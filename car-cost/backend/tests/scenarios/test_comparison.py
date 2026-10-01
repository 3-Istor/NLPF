"""NLPF-44 : delta exact et contributeurs explicables."""

from dataclasses import replace
from decimal import Decimal

import pytest

from carcost.application.compare_scenarios import (
    IncomparableCalculations,
    compare_calculations,
)
from .test_parameterized_calculation import calculate
from carcost.application.scenario import ScenarioParameter
from carcost.domain.engine import PartLine
from carcost.application.run_calculation import CalculationStatus


def test_exact_delta_and_shared_part_are_reported(diamond):
    baseline = calculate(diamond)
    alternative = calculate(
        diamond,
        ScenarioParameter("S", supplier_id="SUP-IT", plant_id="PLT-TR"),
    )
    comparison = compare_calculations(baseline, alternative)

    assert comparison.cost_delta == Decimal("-23.000000")
    assert comparison.top_differences[0].part_ref == "S"
    assert comparison.top_differences[0].delta == Decimal("-23.000000")
    assert comparison.top_differences[0].cumulative_quantity_a == Decimal("23")


def test_identical_scenarios_have_no_difference(diamond):
    calculation = calculate(diamond)
    comparison = compare_calculations(calculation, calculation)

    assert comparison.cost_delta == 0
    assert comparison.top_differences == ()


def test_co2_delta_is_exposed_when_the_carbon_projection_is_available(diamond):
    first = replace(calculate(diamond), total_co2=Decimal("12.500000"))
    second = replace(first, id="calc-2", total_co2=Decimal("11.250000"))

    comparison = compare_calculations(first, second)

    assert comparison.co2_delta == Decimal("-1.250000")


def test_changing_plant_moves_the_co2_delta(diamond):
    """L'usine turque émet plus au transport (0,142 contre 0,021 kg CO2e/kg)."""
    baseline = calculate(diamond)
    turkey = calculate(
        diamond,
        ScenarioParameter("S", supplier_id="SUP-IT", plant_id="PLT-TR"),
    )

    comparison = compare_calculations(baseline, turkey)

    # 23 vis × 1 kg × (0,142 − 0,021).
    assert comparison.co2_delta == Decimal("2.783000")


def test_a_path_plant_change_moves_the_co2_of_that_occurrence_only(diamond):
    """V/B/S passe en Turquie : 15 vis sur 23 changent de transport.

    15 × 1 kg × (0,142 − 0,021) = 1,815. Avant correction le coût bougeait et
    le CO2 non : l'écart CO2 valait zéro.
    """
    baseline = calculate(diamond)
    one_path = calculate(
        diamond,
        ScenarioParameter(
            "S", scope="path", path="V/B/S",
            supplier_id="SUP-IT", plant_id="PLT-TR",
        ),
    )

    comparison = compare_calculations(baseline, one_path)

    assert comparison.co2_delta == Decimal("1.815000")


def test_no_co2_delta_when_one_side_has_an_unknown_co2(diamond):
    """Un prix forcé laisse le transport inconnu : l'écart entre une somme
    complète et une somme partielle mesurerait la pièce manquante, pas le
    choix de sourcing."""
    baseline = calculate(diamond)
    forced = calculate(
        diamond,
        ScenarioParameter(
            "S",
            price_override=Decimal("9.000000"),
            price_override_justification="devis",
        ),
    )

    comparison = compare_calculations(baseline, forced)

    assert comparison.cost_delta == Decimal("-23.000000")
    assert comparison.co2_delta is None


def test_ties_are_ordered_by_part_reference(diamond):
    first = calculate(diamond)
    lines = tuple(
        replace(line, own_contribution=line.own_contribution + Decimal("1"))
        if line.part_ref in {"A", "B"}
        else line
        for line in first.lines
    )
    second = replace(first, id="calc-2", total_cost=first.total_cost + 2, lines=lines)

    comparison = compare_calculations(first, second)

    assert [item.part_ref for item in comparison.top_differences] == ["A", "B"]


def test_only_the_ten_largest_absolute_differences_are_returned(diamond):
    first = calculate(diamond)
    base_lines = tuple(
        PartLine(
            part_ref=f"P-{index:02}", cumulative_quantity=Decimal(1),
            occurrence_count=1, own_unit_cost=Decimal(0),
            own_contribution=Decimal(0), full_unit_cost=Decimal(0),
        )
        for index in range(12)
    )
    changed_lines = tuple(
        replace(
            line,
            own_unit_cost=Decimal(index + 1),
            own_contribution=Decimal(index + 1),
            full_unit_cost=Decimal(index + 1),
        )
        for index, line in enumerate(base_lines)
    )
    before = replace(first, lines=base_lines, total_cost=Decimal(0))
    after = replace(first, id="calc-2", lines=changed_lines, total_cost=Decimal(78))

    comparison = compare_calculations(before, after)

    assert len(comparison.top_differences) == 10
    assert [item.delta for item in comparison.top_differences[:2]] == [
        Decimal(12), Decimal(11)
    ]


def test_different_snapshot_is_rejected(diamond):
    first = calculate(diamond)
    with pytest.raises(IncomparableCalculations, match="même snapshot"):
        compare_calculations(first, replace(first, snapshot_id="other"))


def test_incomplete_calculation_is_not_compared_as_if_missing_prices_were_zero(diamond):
    complete = calculate(diamond)
    incomplete = replace(
        complete,
        id="calc-incomplete",
        status=CalculationStatus.INCOMPLETE,
        parts_without_price=("S",),
    )

    with pytest.raises(IncomparableCalculations, match="incomplet"):
        compare_calculations(complete, incomplete)
