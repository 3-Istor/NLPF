"""Parcourir le graphe pour l'écran : déplier, remonter les emplois, chercher.

Le serveur tient le graphe, le navigateur non. Tout ce qu'une ligne d'arbre
affiche — nombre d'emplois, existence d'enfants, quantité d'arête — est calculé
ici et envoyé tel quel : le front affiche, il ne déduit pas (ADR-0009).

Une ligne d'arbre est identifiée par son **chemin**, pas par sa référence : une
pièce partagée apparaît à plusieurs endroits, et ce sont deux occurrences
distinctes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from ..domain.bom import Bom
from ..domain.text_folding import fold

PATH_SEPARATOR = "/"


class PathNotFound(Exception):
    """Le chemin ne correspond à aucune suite d'arêtes existante."""


@dataclass(frozen=True)
class TreeNode:
    path: str
    part_ref: str
    label: str
    system: str
    valuation_mode: str
    unit: str
    edge_quantity: Decimal
    has_children: bool
    child_count: int
    #: Nombre de parents directs distincts.
    parent_count: int
    #: Nombre de chemins depuis la racine — ce qu'affiche le badge « utilisée à
    #: N endroits ». Les deux diffèrent dès qu'un sous-ensemble est lui-même
    #: monté plusieurs fois.
    occurrence_count: int
    #: Pièces de rechange (SAV) portées par l'arête qui mène à cette ligne.
    #: Affichées à côté de la quantité montée, jamais additionnées par l'écran.
    after_sales_quantity: Decimal = Decimal(0)


@dataclass(frozen=True)
class Occurrence:
    path: str
    path_labels: tuple[str, ...]
    #: Quantité de cette pièce apportée par ce chemin précis, pour un véhicule.
    quantity_on_path: Decimal


@dataclass(frozen=True)
class SearchHit:
    part_ref: str
    label: str
    system: str
    occurrence_count: int
    paths: tuple[str, ...]
    paths_truncated: bool


@dataclass(frozen=True)
class SearchSummary:
    #: Pièces trouvées, au-delà de la limite de la liste renvoyée.
    total_parts: int
    #: Somme de leurs emplacements de montage.
    total_occurrences: int


@dataclass(frozen=True)
class Page:
    items: tuple
    total: int
    limit: int
    offset: int


def root_node(bom: Bom) -> TreeNode:
    return _node(bom, bom.root_ref, bom.root_ref, Decimal(1))


def children_of_path(bom: Bom, path: str, *, limit: int = 50, offset: int = 0) -> Page:
    """Les enfants directs d'une occurrence, et rien d'autre."""
    _resolve(bom, path)
    parent_ref = path.split(PATH_SEPARATOR)[-1]
    children = bom.children_of(parent_ref)

    window = children[offset : offset + limit]
    items = tuple(
        _node(bom, child_ref, f"{path}{PATH_SEPARATOR}{child_ref}", quantity)
        for child_ref, quantity in window
    )
    return Page(items=items, total=len(children), limit=limit, offset=offset)


def where_used(bom: Bom, part_ref: str, *, limit: int = 50, offset: int = 0) -> Page:
    """Tous les chemins qui mènent à cette pièce, avec ce qu'ils apportent."""
    if part_ref not in bom.parts:
        raise PathNotFound(f"référence inconnue : {part_ref}")

    occurrences = tuple(
        Occurrence(
            path=PATH_SEPARATOR.join(chain),
            path_labels=tuple(bom.parts[ref].label for ref in chain),
            quantity_on_path=quantity,
        )
        for chain, quantity in _paths_to(bom, part_ref)
    )
    return Page(
        items=occurrences[offset : offset + limit],
        total=len(occurrences),
        limit=limit,
        offset=offset,
    )


def search_parts(
    bom: Bom, query: str, *, limit: int = 20, max_paths: int = 50
) -> list[SearchHit]:
    """Cherche par référence ou libellé, et renvoie **les chemins**.

    Sans les chemins, le front ne saurait pas quoi déplier pour atteindre le
    résultat : il ne connaît pas le graphe. La comparaison ignore accents et
    casse (`fold`).
    """
    hits: list[SearchHit] = []
    for ref in _matching_refs(bom, query):
        paths = [PATH_SEPARATOR.join(chain) for chain, _ in _paths_to(bom, ref)]
        part = bom.parts[ref]
        hits.append(
            SearchHit(
                part_ref=ref,
                label=part.label,
                system=part.system,
                occurrence_count=len(paths),
                paths=tuple(paths[:max_paths]),
                paths_truncated=len(paths) > max_paths,
            )
        )
        if len(hits) >= limit:
            break
    return hits


def search_summary(bom: Bom, query: str) -> SearchSummary:
    """Ce que la recherche a trouvé en tout, pas seulement ce qu'elle renvoie.

    Sans ces totaux, une liste coupée à `limit` se lit comme un résultat complet.
    """
    refs = list(_matching_refs(bom, query))
    occurrences = sum(len(_paths_to(bom, ref)) for ref in refs)
    return SearchSummary(total_parts=len(refs), total_occurrences=occurrences)


def _matching_refs(bom: Bom, query: str):
    needle = fold(query.strip())
    if not needle:
        return
    for ref in sorted(bom.parts):
        if needle in fold(ref) or needle in fold(bom.parts[ref].label):
            yield ref


# ------------------------------------------------------------------ internes


def _node(bom: Bom, part_ref: str, path: str, edge_quantity: Decimal) -> TreeNode:
    part = bom.parts[part_ref]
    children = bom.children_of(part_ref)
    chain = path.split(PATH_SEPARATOR)
    parent_ref = chain[-2] if len(chain) > 1 else None
    after_sales = next(
        (
            edge.after_sales_quantity
            for edge in bom.edges
            if edge.parent_ref == parent_ref and edge.child_ref == part_ref
        ),
        Decimal(0),
    )
    return TreeNode(
        path=path,
        part_ref=part_ref,
        label=part.label,
        system=part.system,
        valuation_mode=part.valuation_mode.value,
        unit=part.unit,
        edge_quantity=edge_quantity,
        has_children=bool(children),
        child_count=len(children),
        parent_count=len({edge.parent_ref for edge in bom.edges if edge.child_ref == part_ref}),
        occurrence_count=len(_paths_to(bom, part_ref)),
        after_sales_quantity=after_sales,
    )


def _resolve(bom: Bom, path: str) -> Sequence[str]:
    """Un chemin n'est valide que s'il est une vraie suite d'arêtes.

    Deux références qui existent ne font pas un chemin : encore faut-il qu'une
    arête les relie, et que la première soit la racine.
    """
    refs = path.split(PATH_SEPARATOR)
    if not refs or refs[0] != bom.root_ref:
        raise PathNotFound(f"{path} ne part pas de la racine {bom.root_ref}")

    for ref in refs:
        if ref not in bom.parts:
            raise PathNotFound(f"{path} : référence inconnue {ref}")

    for parent_ref, child_ref in zip(refs, refs[1:]):
        if child_ref not in {child for child, _ in bom.children_of(parent_ref)}:
            raise PathNotFound(
                f"{path} : aucune arête ne va de {parent_ref} à {child_ref}"
            )
    return refs


def _paths_to(bom: Bom, target: str) -> list[tuple[tuple[str, ...], Decimal]]:
    """Énumère les chemins racine → pièce, avec la quantité apportée par chacun.

    L'énumération est bornée par le nombre de chemins, pas par la taille du
    graphe : sur cette nomenclature il y en a moins d'un millier.
    """
    found: list[tuple[tuple[str, ...], Decimal]] = []

    def walk(ref: str, chain: tuple[str, ...], quantity: Decimal) -> None:
        if ref == target:
            found.append((chain, quantity))
            return
        for child_ref, edge_quantity in bom.children_of(ref):
            walk(child_ref, chain + (child_ref,), quantity * edge_quantity)

    walk(bom.root_ref, (bom.root_ref,), Decimal(1))
    return found
