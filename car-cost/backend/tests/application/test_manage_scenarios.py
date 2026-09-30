"""NLPF-42 : conserver les réglages sans lancer de calcul."""

from dataclasses import replace
from decimal import Decimal

import pytest

from carcost.application import manage_scenarios
from carcost.application.price_resolution import ParameterNotApplicable
from carcost.application.scenario import Scenario, ScenarioParameter
from fakes import FakeBomRepository, FakeScenarioRepository, FakeSourcingRepository


@pytest.fixture
def repositories(diamond):
    return FakeBomRepository(diamond), FakeScenarioRepository(), FakeSourcingRepository()


def scenario(**changes):
    return replace(
        Scenario(
            id="scn-original", bom_version="bom-test", name="Sourcing Turquie",
            display_currency="EUR", labour_rate=Decimal("42.123456"),
            active_rules=frozenset(),
            parameters=(
                ScenarioParameter(
                    part_ref="S", supplier_id="SUP-IT", plant_id="PLT-TR",
                    purchase_currency="USD", price_override=Decimal("9.123456"),
                    price_override_justification="Offre négociée synthétique",
                ),
                ScenarioParameter(
                    part_ref="S", scope="path", path="V/B/S",
                    supplier_id="SUP-DE", plant_id="PLT-DE", purchase_currency="RUB",
                ),
                ScenarioParameter(part_ref="A", labour_minutes=Decimal("21.2345")),
            ),
        ),
        **changes,
    )


def test_creation_keeps_all_settings_and_disabled_rules(repositories):
    boms, scenarios, sourcing = repositories
    original = scenario()

    manage_scenarios.create_scenario(original, boms, scenarios, sourcing)

    assert scenarios.get(original.id) == original


def test_duplicate_has_its_own_identity_name_and_editable_parameters(repositories):
    boms, scenarios, sourcing = repositories
    original = scenario()
    manage_scenarios.create_scenario(original, boms, scenarios, sourcing)

    copied = manage_scenarios.duplicate_scenario(
        original.id, name="Alternative Allemagne", scenario_id="scn-copy",
        boms=boms, scenarios=scenarios, sourcing=sourcing,
    )
    assert copied == replace(original, id="scn-copy", name="Alternative Allemagne")
    manage_scenarios.put_parameter(
        copied.id, ScenarioParameter(part_ref="S", purchase_currency="EUR"),
        boms, scenarios, sourcing,
    )

    assert scenarios.get(original.id) == original
    assert scenarios.get(copied.id).parameter_for("S").purchase_currency == "EUR"


def test_model_detaches_mutable_collections():
    parameters = [ScenarioParameter(part_ref="S")]
    rules = {"labour"}
    original = scenario(parameters=parameters, active_rules=rules)
    parameters.clear()
    rules.clear()

    assert original.parameters == (ScenarioParameter(part_ref="S"),)
    assert original.active_rules == frozenset({"labour"})


@pytest.mark.parametrize("scope,path", [("part", None), ("path", "V/A/UNKNOWN")])
def test_creation_rejects_unknown_part_before_any_write(repositories, scope, path):
    boms, scenarios, sourcing = repositories
    original = scenario(parameters=(ScenarioParameter("UNKNOWN", scope, path),))

    with pytest.raises(ParameterNotApplicable, match="UNKNOWN.*n'existe pas"):
        manage_scenarios.create_scenario(original, boms, scenarios, sourcing)

    assert scenarios.scenarios == {}


def test_parameter_update_rejects_unknown_part_before_any_write(repositories):
    boms, scenarios, sourcing = repositories
    original = scenario()
    manage_scenarios.create_scenario(original, boms, scenarios, sourcing)

    with pytest.raises(ParameterNotApplicable, match="UNKNOWN"):
        manage_scenarios.put_parameter(
            original.id, ScenarioParameter("UNKNOWN"), boms, scenarios, sourcing,
        )

    assert scenarios.get(original.id) == original


@pytest.mark.parametrize("parameter", [
    ScenarioParameter("S", "other"),
    ScenarioParameter("S", "part", "V/A/S"),
    ScenarioParameter("S", "path"),
    ScenarioParameter("S", "path", "V/S"),
    ScenarioParameter("S", "path", "A/S"),
    ScenarioParameter("S", "path", "V/A"),
])
def test_scope_and_complete_path_are_validated(repositories, parameter):
    boms, scenarios, sourcing = repositories

    with pytest.raises(manage_scenarios.InvalidScenario):
        manage_scenarios.create_scenario(
            scenario(parameters=(parameter,)), boms, scenarios, sourcing,
        )
    assert scenarios.scenarios == {}


def test_part_and_two_occurrence_targets_coexist(repositories):
    boms, scenarios, sourcing = repositories
    original = scenario()
    manage_scenarios.create_scenario(original, boms, scenarios, sourcing)
    for path in ("V/A/S", "V/B/S"):
        manage_scenarios.put_parameter(
            original.id, ScenarioParameter("S", "path", path, purchase_currency="EUR"),
            boms, scenarios, sourcing,
        )
    reloaded = scenarios.get(original.id)

    assert reloaded.parameter_for("S") == original.parameter_for("S")
    assert {p.path for p in reloaded.parameters if p.part_ref == "S"} == {
        None, "V/A/S", "V/B/S",
    }
    assert len(reloaded.parameters) == 4


def test_duplicate_target_is_rejected_instead_of_losing_a_setting(repositories):
    boms, scenarios, sourcing = repositories
    with pytest.raises(manage_scenarios.InvalidScenario, match="cible"):
        manage_scenarios.create_scenario(
            scenario(parameters=(ScenarioParameter("S"), ScenarioParameter("S"))),
            boms, scenarios, sourcing,
        )
    assert scenarios.scenarios == {}


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_is_rejected(repositories, name):
    boms, scenarios, sourcing = repositories
    with pytest.raises(manage_scenarios.InvalidScenario, match="nom"):
        manage_scenarios.create_scenario(scenario(name=name), boms, scenarios, sourcing)


def test_purchase_currency_is_not_applicable_to_manufactured_parts(repositories):
    boms, scenarios, sourcing = repositories
    with pytest.raises(ParameterNotApplicable, match="A.*fabriqué"):
        manage_scenarios.create_scenario(
            scenario(parameters=(ScenarioParameter("A", purchase_currency="USD"),)),
            boms, scenarios, sourcing,
        )


@pytest.mark.parametrize("changes", [
    {"display_currency": "usd"},
    {"labour_rate": Decimal("42.1234567")},
    {"labour_rate": Decimal("NaN")},
    {"labour_rate": Decimal("-1")},
    {"labour_rate": Decimal("1000000000000")},
    {"parameters": (ScenarioParameter("S", purchase_currency="US"),)},
    {"parameters": (ScenarioParameter(
        "S", price_override=Decimal("1.1234567"), price_override_justification="test",
    ),)},
    {"parameters": (ScenarioParameter("A", labour_minutes=Decimal("12.34567")),)},
    {"parameters": (ScenarioParameter("A", labour_minutes=Decimal("-0.0001")),)},
    {"parameters": (ScenarioParameter("S", plant_id="PLT-TR"),)},
])
def test_unstorable_settings_are_rejected_without_rounding(repositories, changes):
    boms, scenarios, sourcing = repositories
    with pytest.raises(manage_scenarios.InvalidScenario):
        manage_scenarios.create_scenario(scenario(**changes), boms, scenarios, sourcing)
    assert scenarios.scenarios == {}


def test_duplicate_cannot_reuse_source_identity(repositories):
    boms, scenarios, sourcing = repositories
    original = scenario()
    manage_scenarios.create_scenario(original, boms, scenarios, sourcing)
    with pytest.raises(manage_scenarios.InvalidScenario, match="identité"):
        manage_scenarios.duplicate_scenario(
            original.id, name="Copie", scenario_id=original.id,
            boms=boms, scenarios=scenarios, sourcing=sourcing,
        )
    assert scenarios.get(original.id) == original


def test_purchase_currency_change_marks_previous_calculation_stale():
    from datetime import datetime, timezone

    from carcost.application.calculation_state import CalculationState, state_of
    from carcost.application.run_calculation import input_digest
    from carcost.domain.prices import PriceSnapshot

    snapshot = PriceSnapshot(
        id="snp", taken_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        currency="EUR", source="test", prices={"S": Decimal("1")},
    )
    before = scenario(parameters=(ScenarioParameter("S", purchase_currency="EUR"),))
    after = replace(before, parameters=(ScenarioParameter("S", purchase_currency="USD"),))
    state, reason = state_of(after, snapshot, last_digest=input_digest(before, snapshot))

    assert state is CalculationState.PARAMETERS_CHANGED
    assert reason == "parameters"
    renamed_copy = replace(before, id="scn-copy", name="Autre nom")
    assert input_digest(renamed_copy, snapshot) == input_digest(before, snapshot)
