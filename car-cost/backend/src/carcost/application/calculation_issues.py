"""Les lignes d'un calcul dont le prix n'est pas sain, avec de quoi les trouver.

La synthèse les compte ; ce n'est pas assez quand une panne touche trente
pièces. Chaque ligne porte un chemin pour que l'écran déplie l'arbre jusqu'à
elle (docs/api.md §4.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..domain.bom import Bom
from .run_calculation import Calculation, PriceStatus, first_path_of_each_part

#: Les noms de `calculation_issue_kind` en base, du plus grave au moins grave :
#: une pièce sans prix rend le total faux, un repli le rend seulement ancien.
ISSUE_KINDS = {
    PriceStatus.MISSING: "MISSING_PRICE",
    PriceStatus.QUARANTINED: "QUARANTINED",
    PriceStatus.FALLBACK: "FALLBACK",
}
_SEVERITY = {kind: rank for rank, kind in enumerate(ISSUE_KINDS.values())}


@dataclass(frozen=True)
class Issue:
    kind: str
    part_ref: str
    label: str
    system: str
    #: Un chemin parmi d'autres ; le where-used donne les autres.
    path: str
    cumulative_quantity: Decimal
    occurrence_count: int


def calculation_issues(calculation: Calculation, bom: Bom) -> tuple[Issue, ...]:
    paths = first_path_of_each_part(bom)
    lines = {line.part_ref: line for line in calculation.lines}
    issues = [
        Issue(
            kind=ISSUE_KINDS[status],
            part_ref=ref,
            label=bom.parts[ref].label,
            system=bom.parts[ref].system,
            path=paths[ref],
            cumulative_quantity=lines[ref].cumulative_quantity,
            occurrence_count=lines[ref].occurrence_count,
        )
        for ref, status in calculation.price_statuses.items()
    ]
    return tuple(sorted(issues, key=lambda issue: (_SEVERITY[issue.kind], issue.part_ref)))
