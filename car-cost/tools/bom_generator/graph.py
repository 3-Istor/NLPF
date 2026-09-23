"""Parcours du graphe : tri topologique, quantités cumulées, profondeur.

Les quantités cumulées sont calculées **deux fois**, par deux algorithmes
différents :

  - par programmation dynamique en ordre topologique — ce que fera le moteur ;
  - par énumération de tous les chemins — la définition, littéralement.

Si les deux ne coïncident pas, le jeu de données est refusé. Sans ce
recoupement, les valeurs de contrôle ne vaudraient rien : elles seraient la
sortie de l'algorithme qu'elles sont censées vérifier.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .model import Bom, BomError

MAX_PATHS = 5_000_000


def children_index(bom: Bom) -> dict[str, list[tuple[str, Decimal]]]:
    index: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    for edge in bom.edges:
        index[edge.parent_ref].append((edge.child_ref, edge.quantity))
    return index


def parents_index(bom: Bom) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for edge in bom.edges:
        index[edge.child_ref].append(edge.parent_ref)
    return index


def topological_order(bom: Bom) -> list[str]:
    """Ordre parent → enfant. Lève si le graphe contient un cycle.

    L'acyclicité n'est pas supposée : elle est établie ici, et c'est le seul
    endroit du jeu de données qui puisse l'affirmer.
    """
    children = children_index(bom)
    indegree = {ref: 0 for ref in bom.parts}
    for edge in bom.edges:
        indegree[edge.child_ref] += 1

    ready = sorted(ref for ref, deg in indegree.items() if deg == 0)
    order: list[str] = []
    while ready:
        ref = ready.pop(0)
        order.append(ref)
        for child_ref, _ in children[ref]:
            indegree[child_ref] -= 1
            if indegree[child_ref] == 0:
                ready.append(child_ref)
        ready.sort()

    if len(order) != len(bom.parts):
        remaining = sorted(set(bom.parts) - set(order))
        raise BomError(
            f"cycle détecté : {len(remaining)} pièces ne sont jamais atteignables "
            f"en ordre topologique, par exemple {remaining[:5]}"
        )
    return order


def roots(bom: Bom) -> list[str]:
    has_parent = {edge.child_ref for edge in bom.edges}
    return sorted(ref for ref in bom.parts if ref not in has_parent)


def orphans(bom: Bom) -> list[str]:
    """Pièces déclarées mais employées nulle part (la racine mise à part)."""
    return [ref for ref in roots(bom) if ref != bom.root_ref]


def cumulative_quantities(bom: Bom) -> dict[str, Decimal]:
    """Quantité nécessaire pour UN véhicule, par programmation dynamique."""
    children = children_index(bom)
    totals = {ref: Decimal(0) for ref in bom.parts}
    totals[bom.root_ref] = Decimal(1)
    for ref in topological_order(bom):
        parent_quantity = totals[ref]
        if parent_quantity == 0:
            continue
        for child_ref, quantity in children[ref]:
            totals[child_ref] += parent_quantity * quantity
    return totals


def path_counts(bom: Bom) -> dict[str, int]:
    """Nombre de chemins depuis la racine — le « utilisée à N endroits »."""
    children = children_index(bom)
    counts = {ref: 0 for ref in bom.parts}
    counts[bom.root_ref] = 1
    for ref in topological_order(bom):
        if counts[ref] == 0:
            continue
        for child_ref, _ in children[ref]:
            counts[child_ref] += counts[ref]
    return counts


def cumulative_quantities_by_enumeration(bom: Bom) -> dict[str, Decimal]:
    """La définition, littéralement : somme sur tous les chemins des produits.

    Coûteux par construction — c'est le prix du recoupement.
    """
    children = children_index(bom)
    totals = {ref: Decimal(0) for ref in bom.parts}
    visited_paths = 0

    stack: list[tuple[str, Decimal]] = [(bom.root_ref, Decimal(1))]
    while stack:
        ref, quantity = stack.pop()
        totals[ref] += quantity
        visited_paths += 1
        if visited_paths > MAX_PATHS:
            raise BomError(
                "énumération des chemins interrompue : plus de "
                f"{MAX_PATHS} chemins, le recoupement n'est plus praticable"
            )
        for child_ref, child_quantity in children[ref]:
            stack.append((child_ref, quantity * child_quantity))

    return totals


def max_depth(bom: Bom) -> int:
    """Profondeur du plus long chemin, en arêtes, depuis la racine."""
    children = children_index(bom)
    depth = {ref: -1 for ref in bom.parts}
    depth[bom.root_ref] = 0
    for ref in topological_order(bom):
        if depth[ref] < 0:
            continue
        for child_ref, _ in children[ref]:
            depth[child_ref] = max(depth[child_ref], depth[ref] + 1)
    return max(depth.values())


def depth_of(bom: Bom) -> dict[str, int]:
    children = children_index(bom)
    depth = {ref: -1 for ref in bom.parts}
    depth[bom.root_ref] = 0
    for ref in topological_order(bom):
        if depth[ref] < 0:
            continue
        for child_ref, _ in children[ref]:
            depth[child_ref] = max(depth[child_ref], depth[ref] + 1)
    return depth


def rolled_up_mass(bom: Bom) -> dict[str, Decimal]:
    """Masse d'un ensemble = somme des masses de ses enfants.

    Renseignée pour information sur les ensembles fabriqués, qui n'ont pas de
    masse propre : c'est une donnée calculée, jamais une donnée saisie.
    """
    children = children_index(bom)
    mass: dict[str, Decimal] = {}
    for ref in reversed(topological_order(bom)):
        part = bom.parts[ref]
        if part.mass_kg is not None:
            mass[ref] = part.mass_kg
            continue
        total = Decimal(0)
        for child_ref, quantity in children[ref]:
            total += quantity * mass.get(child_ref, Decimal(0))
        mass[ref] = total
    return mass
