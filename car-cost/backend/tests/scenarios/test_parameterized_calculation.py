"""NLPF-43 : le scénario pilote réellement le moteur."""

from datetime import datetime, timezone
from decimal import Decimal

from carcost.application.price_resolution import resolve_unit_prices
from carcost.application.run_calculation import run_calculation
from carcost.application.scenario import Scenario, ScenarioParameter
from carcost.domain.prices import PriceSnapshot
from fakes import FakeSourcingRepository

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def calculate(diamond, *parameters):
    scenario = Scenario(
        id="scn", name="Essai", bom_version="bom-test",
        display_currency="EUR", labour_rate=Decimal("60"),
        parameters=parameters,
    )
    sourcing = FakeSourcingRepository().sourcing
    snapshot = PriceSnapshot(
        id="snp", taken_at=NOW, currency="EUR", source="test",
        prices={"S": Decimal("10")},
    )
    return run_calculation(
        bom=diamond,
        scenario=scenario,
        snapshot=snapshot,
        resolved=resolve_unit_prices(diamond, sourcing, snapshot, scenario),
        now=NOW,
        calculation_id="calc",
    )


def test_origin_change_is_multiplied_by_shared_part_cumulative_quantity(diamond):
    baseline = calculate(diamond)
    turkey = calculate(
        diamond,
        ScenarioParameter("S", supplier_id="SUP-IT", plant_id="PLT-TR"),
    )

    assert baseline.total_cost == Decimal("395.000000")
    assert turkey.total_cost == Decimal("372.000000")
    assert baseline.total_cost - turkey.total_cost == Decimal("23.000000")


def test_path_override_only_changes_the_targeted_occurrence(diamond):
    calculation = calculate(
        diamond,
        ScenarioParameter(
            "S", "path", "V/A/S", supplier_id="SUP-IT", plant_id="PLT-TR"
        ),
    )

    # 8 vis sous A à 9 €, 15 sous B à 10 €, plus 165 € de main-d'œuvre.
    assert calculation.total_cost == Decimal("387.000000")
    assert calculation.path_own_unit_costs["V/A/S"] == Decimal("9.000000")
    assert calculation.path_full_unit_costs["V/A"] == Decimal("66.000000")
    assert calculation.part_own_unit_costs["S"] == Decimal("10.000000")
    assert calculation.lines_by_ref["S"].own_contribution == Decimal("222.000000")
    assert sum(
        line.own_contribution for line in calculation.lines
    ) == calculation.total_cost


def test_path_parameter_replaces_the_part_target_as_a_whole(diamond):
    calculation = calculate(
        diamond,
        ScenarioParameter("S", supplier_id="SUP-DE"),
        ScenarioParameter("S", "path", "V/A/S", purchase_currency="EUR"),
    )

    # Portée pièce : 12 €. Sur V/A/S, la cible chemin reprend le sourcing par
    # défaut à 10 € ; elle n'hérite pas du fournisseur SUP-DE.
    assert calculation.total_cost == Decimal("425.000000")


def test_labour_override_and_active_rule_are_applied(diamond):
    changed = calculate(diamond, ScenarioParameter("A", labour_minutes=Decimal("60")))
    disabled = Scenario(
        id="scn", name="Sans main-d'œuvre", bom_version="bom-test",
        display_currency="EUR", labour_rate=Decimal("60"),
        active_rules=frozenset(),
    )
    sourcing = FakeSourcingRepository().sourcing
    snapshot = PriceSnapshot(
        id="snp", taken_at=NOW, currency="EUR", source="test",
        prices={"S": Decimal("10")},
    )
    without_labour = run_calculation(
        bom=diamond, scenario=disabled, snapshot=snapshot,
        resolved=resolve_unit_prices(diamond, sourcing, snapshot, disabled),
        now=NOW, calculation_id="calc-disabled",
    )

    assert changed.total_cost == Decimal("455.000000")
    assert without_labour.total_cost == Decimal("230.000000")


def test_same_scenario_and_snapshot_are_reproducible(diamond):
    first = calculate(diamond)
    second = calculate(diamond)

    assert first.total_cost == second.total_cost
    assert first.input_digest == second.input_digest
