"""Le contrôle d'intégrité d'une nomenclature, avant qu'elle ne serve.

La base garantit ce qui se déclare (arête unique, parent fabriqué, quantité
positive) ; elle ne sait pas prouver l'acyclicité, ni l'absence d'orphelin, ni
qu'une seule pièce est sans parent. Ce module contrôle tout, y compris ce que la
base refuserait aussi : un import refusé doit dire toutes ses fautes en une
fois, pas une par tentative de `COPY`.

Tout chemin qui renseigne `bom_version.validated_at` passe par ici.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .bom import Bom


@dataclass(frozen=True)
class Violation:
    code: str
    message: str
    part_ref: str | None = None


def validate_bom(bom: Bom) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    violations += _structure(bom)
    violations += _valuation(bom)
    return tuple(violations)


def _structure(bom: Bom) -> list[Violation]:
    violations: list[Violation] = []

    try:
        bom.topological_order()
    except ValueError as cycle:
        violations.append(Violation("CYCLE", str(cycle)))

    parents: dict[str, set[str]] = {ref: set() for ref in bom.parts}
    for edge in bom.edges:
        parents[edge.child_ref].add(edge.parent_ref)

    if parents[bom.root_ref]:
        violations.append(
            Violation(
                "ROOT_HAS_PARENT",
                f"la racine {bom.root_ref} est employée sous "
                f"{sorted(parents[bom.root_ref])}",
                bom.root_ref,
            )
        )

    for ref in sorted(bom.parts):
        if ref != bom.root_ref and not parents[ref]:
            violations.append(
                Violation(
                    "ORPHAN",
                    f"{ref} est orpheline : employée nulle part, elle serait "
                    f"absente du total",
                    ref,
                )
            )

    pairs = Counter((edge.parent_ref, edge.child_ref) for edge in bom.edges)
    for (parent, child), count in sorted(pairs.items()):
        if count > 1:
            violations.append(
                Violation(
                    "DUPLICATE_EDGE",
                    f"arête {parent} → {child} présente {count} fois : sa quantité "
                    f"serait comptée {count} fois",
                    child,
                )
            )

    for edge in bom.edges:
        if edge.quantity <= 0:
            violations.append(
                Violation(
                    "NON_POSITIVE_QUANTITY",
                    f"arête {edge.parent_ref} → {edge.child_ref} : quantité "
                    f"{edge.quantity}",
                    edge.child_ref,
                )
            )

    return violations


def _valuation(bom: Bom) -> list[Violation]:
    """ADR-0008 : achetée ⇒ feuille sans main-d'œuvre ; fabriquée ⇒ enfants et
    main-d'œuvre. Le prix n'est pas une donnée de la pièce dans le domaine : il
    se contrôle là où il entre, au chargement du catalogue."""
    violations: list[Violation] = []
    for ref in sorted(bom.parts):
        part = bom.parts[ref]
        has_children = bool(bom.children_of(ref))
        if part.is_purchased:
            if has_children:
                violations.append(
                    Violation(
                        "PURCHASED_WITH_CHILDREN",
                        f"{ref} est achetée et porte des enfants : son contenu "
                        f"serait compté deux fois",
                        ref,
                    )
                )
            if part.labour_minutes is not None:
                violations.append(
                    Violation(
                        "PURCHASED_WITH_LABOUR",
                        f"{ref} est achetée et porte un temps de main-d'œuvre",
                        ref,
                    )
                )
        else:
            if not has_children:
                violations.append(
                    Violation(
                        "MANUFACTURED_WITHOUT_CHILDREN",
                        f"{ref} est fabriquée et n'a aucun enfant",
                        ref,
                    )
                )
            if part.labour_minutes is None:
                violations.append(
                    Violation(
                        "MANUFACTURED_WITHOUT_LABOUR",
                        f"{ref} est fabriquée sans temps de main-d'œuvre",
                        ref,
                    )
                )
        if part.carbon_factor < 0:
            violations.append(
                Violation(
                    "NEGATIVE_CARBON_FACTOR",
                    f"{ref} : facteur carbone {part.carbon_factor}",
                    ref,
                )
            )
    return violations
