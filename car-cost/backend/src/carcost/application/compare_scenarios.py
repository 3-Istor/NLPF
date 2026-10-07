"""Comparer deux résultats produits par le même moteur et le même snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .run_calculation import Calculation, CalculationStatus


class IncomparableCalculations(Exception):
    """Les deux calculs ne partagent pas les entrées qui doivent rester fixes."""


@dataclass(frozen=True)
class ContributionDelta:
    part_ref: str
    contribution_a: Decimal
    contribution_b: Decimal
    delta: Decimal
    cumulative_quantity_a: Decimal
    cumulative_quantity_b: Decimal


@dataclass(frozen=True)
class ScenarioComparison:
    calculation_a_id: str
    calculation_b_id: str
    snapshot_id: str
    display_currency: str
    total_a: Decimal
    total_b: Decimal
    cost_delta: Decimal
    co2_delta: Decimal | None
    top_differences: tuple[ContributionDelta, ...]


def compare_calculations(
    calculation_a: Calculation,
    calculation_b: Calculation,
    *,
    top: int = 10,
) -> ScenarioComparison:
    if any(
        calculation.status is CalculationStatus.INCOMPLETE
        for calculation in (calculation_a, calculation_b)
    ):
        raise IncomparableCalculations(
            "un calcul incomplet ne peut pas être comparé : un prix manquant n'est pas zéro"
        )
    if calculation_a.snapshot_id != calculation_b.snapshot_id:
        raise IncomparableCalculations(
            "les scénarios doivent être calculés avec le même snapshot de prix"
        )
    if calculation_a.display_currency != calculation_b.display_currency:
        raise IncomparableCalculations(
            "les scénarios doivent utiliser la même devise d'affichage"
        )

    lines_a = {line.part_ref: line for line in calculation_a.lines}
    lines_b = {line.part_ref: line for line in calculation_b.lines}
    differences = []
    for part_ref in sorted(set(lines_a) | set(lines_b)):
        line_a = lines_a.get(part_ref)
        line_b = lines_b.get(part_ref)
        contribution_a = (
            line_a.own_contribution
            if line_a is not None and line_a.own_contribution is not None
            else Decimal(0)
        )
        contribution_b = (
            line_b.own_contribution
            if line_b is not None and line_b.own_contribution is not None
            else Decimal(0)
        )
        delta = contribution_b - contribution_a
        if delta == 0:
            continue
        differences.append(
            ContributionDelta(
                part_ref=part_ref,
                contribution_a=contribution_a,
                contribution_b=contribution_b,
                delta=delta,
                cumulative_quantity_a=(
                    line_a.cumulative_quantity if line_a else Decimal(0)
                ),
                cumulative_quantity_b=(
                    line_b.cumulative_quantity if line_b else Decimal(0)
                ),
            )
        )

    differences.sort(key=lambda item: (-abs(item.delta), item.part_ref))
    # Un écart entre deux sommes partielles mesurerait surtout les pièces
    # manquantes : sans CO2 complet des deux côtés, pas d'écart annoncé.
    co2_delta = None
    if calculation_a.co2_is_complete and calculation_b.co2_is_complete:
        co2_delta = calculation_b.total_co2 - calculation_a.total_co2
    return ScenarioComparison(
        calculation_a_id=calculation_a.id,
        calculation_b_id=calculation_b.id,
        snapshot_id=calculation_a.snapshot_id,
        display_currency=calculation_a.display_currency,
        total_a=calculation_a.total_cost,
        total_b=calculation_b.total_cost,
        cost_delta=calculation_b.total_cost - calculation_a.total_cost,
        co2_delta=co2_delta,
        top_differences=tuple(differences[:top]),
    )
