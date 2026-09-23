"""Le moteur de coût : programmation dynamique en ordre topologique (ADR-0005).

Deux parcours de sens opposés, et c'est voulu :

  - les **quantités cumulées** descendent, des parents vers les enfants ;
  - les **coûts unitaires** remontent, des enfants vers les parents.

Chaque pièce est évaluée exactement une fois, quel que soit le nombre de chemins
qui mènent à elle. Un test à compteur d'appels le prouve.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .bom import Bom
from .scenario import CalculationInput

MINUTES_PER_HOUR = Decimal(60)


@dataclass(frozen=True)
class PartLine:
    """Une ligne de la vue agrégée : une pièce, pas une occurrence.

    `own_contribution` est la seule grandeur qui se somme : additionner les
    `full_unit_cost` reviendrait à compter chaque ensemble puis son contenu.
    """

    part_ref: str
    cumulative_quantity: Decimal
    occurrence_count: int
    own_unit_cost: Decimal | None
    own_contribution: Decimal | None
    full_unit_cost: Decimal | None


@dataclass(frozen=True)
class CalculationResult:
    lines: tuple[PartLine, ...]
    total_cost: Decimal
    parts_without_price: tuple[str, ...]

    def line(self, part_ref: str) -> PartLine:
        for line in self.lines:
            if line.part_ref == part_ref:
                return line
        raise KeyError(part_ref)

    @property
    def is_incomplete(self) -> bool:
        """Il manque au moins un prix. Le total n'est pas un total fiable."""
        return bool(self.parts_without_price)


def compute(inputs: CalculationInput) -> CalculationResult:
    bom = inputs.bom
    order = bom.topological_order()

    cumulative, occurrences = _quantities(bom, order)
    own_unit_cost, missing = _own_unit_costs(inputs)
    full_unit_cost = _roll_up(bom, order, own_unit_cost)

    lines = []
    total = Decimal(0)
    for ref in order:
        own = own_unit_cost[ref]
        contribution = None if own is None else cumulative[ref] * own
        if contribution is not None:
            total += contribution
        lines.append(
            PartLine(
                part_ref=ref,
                cumulative_quantity=cumulative[ref],
                occurrence_count=occurrences[ref],
                own_unit_cost=own,
                own_contribution=contribution,
                full_unit_cost=full_unit_cost[ref],
            )
        )

    return CalculationResult(
        lines=tuple(lines),
        total_cost=total,
        parts_without_price=tuple(missing),
    )


def _quantities(
    bom: Bom, order: tuple[str, ...]
) -> tuple[dict[str, Decimal], dict[str, int]]:
    """Ce qu'il faut de chaque pièce pour UN véhicule, et en combien d'endroits.

    Une pièce partagée reçoit la somme des apports de tous ses parents : c'est
    ce qui distingue un graphe d'un arbre.
    """
    cumulative = {ref: Decimal(0) for ref in bom.parts}
    occurrences = {ref: 0 for ref in bom.parts}
    cumulative[bom.root_ref] = Decimal(1)
    occurrences[bom.root_ref] = 1

    for ref in order:
        if occurrences[ref] == 0:
            continue
        for child_ref, quantity in bom.children_of(ref):
            cumulative[child_ref] += cumulative[ref] * quantity
            occurrences[child_ref] += occurrences[ref]

    return cumulative, occurrences


def _own_unit_costs(
    inputs: CalculationInput,
) -> tuple[dict[str, Decimal | None], list[str]]:
    """Le coût PROPRE d'une unité : le prix d'achat, ou la seule main-d'œuvre.

    Sur une pièce achetée on ne somme jamais les enfants — elle n'en a pas.
    Sur un ensemble fabriqué on ne cherche jamais de prix : un prix qui
    traînerait dans le catalogue resterait sans effet (ADR-0008).
    """
    prices = inputs.unit_prices
    labour_is_active = "labour" in inputs.active_rules

    costs: dict[str, Decimal | None] = {}
    missing: list[str] = []

    for ref, part in inputs.bom.parts.items():
        if part.is_purchased:
            if ref in prices:
                costs[ref] = prices[ref]
            else:
                costs[ref] = None
                missing.append(ref)
        elif labour_is_active and part.labour_minutes is not None:
            costs[ref] = part.labour_minutes / MINUTES_PER_HOUR * inputs.labour_rate
        else:
            costs[ref] = Decimal(0)

    return costs, sorted(missing)


def _roll_up(
    bom: Bom, order: tuple[str, ...], own_unit_cost: dict[str, Decimal | None]
) -> dict[str, Decimal | None]:
    """Le coût unitaire COMPLET : le propre, plus celui des enfants.

    C'est ce qu'on affiche sur une ligne de l'arbre ; il ne se somme pas entre
    niveaux. Un enfant sans prix rend son parent incalculable plutôt que
    faussement bon marché.
    """
    rolled: dict[str, Decimal | None] = {}
    for ref in reversed(order):
        own = own_unit_cost[ref]
        if own is None:
            rolled[ref] = None
            continue
        total = own
        for child_ref, quantity in bom.children_of(ref):
            child_cost = rolled[child_ref]
            if child_cost is None:
                total = None
                break
            total += quantity * child_cost
        rolled[ref] = total
    return rolled
