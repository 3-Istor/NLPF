"""Figer un calcul sous un nom, le renommer, comparer deux gels (ADR-0014)."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from carcost.application import manage_scenarios
from carcost.application.compare_scenarios import IncomparableCalculations
from carcost.application.freeze_calculation import (
    compare_snapshots, freeze_scenario, rename_snapshot,
)
from carcost.application.ports import (
    BomVersionNotValidated, CalculationSnapshotNotFound, SnapshotNameTaken,
)
from carcost.application.price_resolution import resolve_unit_prices
from carcost.application.run_calculation import (
    CalculationStatus, input_digest, run_calculation,
)
from carcost.application.scenario import Scenario, ScenarioParameter
from carcost.domain.calculation_snapshot import InvalidSnapshotName
from carcost.domain.prices import PriceSnapshot
from fakes import (
    FakeBomRepository, FakeCalculationRepository,
    FakeCalculationSnapshotRepository, FakeScenarioRepository,
    FakeSourcingRepository,
)

NOW = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)
LATER = NOW + timedelta(hours=2)


def prices(snapshot_id: str = "snp-prix-1", **values: str) -> PriceSnapshot:
    return PriceSnapshot(
        id=snapshot_id, taken_at=NOW - timedelta(minutes=5), currency="EUR",
        source="mock",
        prices={ref: Decimal(value) for ref, value in values.items()},
    )


class World:
    """Les doubles d'un gel, et un `calculate` réel qui enregistre son calcul."""

    def __init__(self, diamond, *, validated: bool = True):
        self.boms = FakeBomRepository(diamond, validated=validated)
        self.sourcing = FakeSourcingRepository()
        self.scenarios = FakeScenarioRepository()
        self.calculations = FakeCalculationRepository()
        self.snapshots_repo = FakeCalculationSnapshotRepository()
        self.calls: list[Scenario] = []

    def calculator(self, price_snapshot: PriceSnapshot, *, after=None):
        def calculate(scenario: Scenario):
            bom = self.boms.load(scenario.bom_version)
            resolved = resolve_unit_prices(
                bom, self.sourcing.load(scenario.bom_version), price_snapshot,
                scenario,
            )
            calculation = run_calculation(
                bom=bom, scenario=scenario, snapshot=price_snapshot,
                resolved=resolved, now=NOW,
                calculation_id=f"calc-{len(self.calculations.order) + 1}",
            )
            self.calculations.save(calculation)
            self.calls.append(scenario)
            if after is not None:
                after(scenario)
            return calculation

        return calculate

    def freeze(self, name: str, calculate, *, snapshot_id: str = "csn-1",
               scenario_id: str = "scn-etude", now: datetime = NOW):
        return freeze_scenario(
            scenario_id, name, scenarios=self.scenarios, boms=self.boms,
            snapshots_repo=self.snapshots_repo, calculate=calculate,
            snapshot_id=snapshot_id, now=now,
        )


def study(**changes) -> Scenario:
    return replace(
        Scenario(
            id="scn-etude", bom_version="bom-test", name="Étude Turquie",
            display_currency="EUR", labour_rate=Decimal("41.500000"),
            active_rules=frozenset({"labour"}),
            parameters=(
                ScenarioParameter(
                    part_ref="S", supplier_id="SUP-IT", plant_id="PLT-TR",
                ),
                ScenarioParameter(
                    part_ref="S", scope="path", path="V/B/S",
                    supplier_id="SUP-DE", plant_id="PLT-DE",
                ),
            ),
        ),
        **changes,
    )


@pytest.fixture
def world(diamond):
    world = World(diamond)
    manage_scenarios.create_scenario(
        study(), world.boms, world.scenarios, world.sourcing,
    )
    return world


def rebuilt(snapshot) -> Scenario:
    """Le scénario que la copie décrit, sans relire le scénario vivant."""
    return Scenario(
        id=snapshot.scenario_id, bom_version=snapshot.bom_version,
        display_currency=snapshot.display_currency,
        labour_rate=snapshot.labour_rate, active_rules=snapshot.active_rules,
        parameters=tuple(
            ScenarioParameter(**asdict(parameter))
            for parameter in snapshot.parameters
        ),
        name=snapshot.scenario_name,
    )


def test_freezing_runs_a_calculation_and_copies_the_parameters_it_used(world):
    price_snapshot = prices(S="10.000000")

    snapshot = world.freeze("Référence T3", world.calculator(price_snapshot))

    assert len(world.calculations.order) == 1
    calculation = world.calculations.get(world.calculations.order[0])
    assert snapshot.calculation_id == calculation.id
    assert snapshot.price_snapshot_id == "snp-prix-1"
    assert snapshot.scenario_name == "Étude Turquie"
    assert len(snapshot.parameters) == 2
    assert input_digest(rebuilt(snapshot), price_snapshot) == calculation.input_digest
    assert world.snapshots_repo.get(snapshot.id) == snapshot


def test_the_copy_is_the_scenario_that_was_calculated_even_if_it_changes_meanwhile(
    world,
):
    price_snapshot = prices(S="10.000000")
    concurrent = ScenarioParameter(part_ref="A", labour_minutes=Decimal("99.0000"))

    def change_meanwhile(scenario):
        world.scenarios.put_parameter(scenario.id, concurrent)

    snapshot = world.freeze(
        "Référence T3", world.calculator(price_snapshot, after=change_meanwhile),
    )

    calculation = world.calculations.get(snapshot.calculation_id)
    assert input_digest(rebuilt(snapshot), price_snapshot) == calculation.input_digest
    assert all(parameter.part_ref != "A" for parameter in snapshot.parameters)
    assert concurrent in world.scenarios.get("scn-etude").parameters


def test_changing_the_scenario_after_freezing_changes_nothing_in_the_snapshot(world):
    snapshot = world.freeze("Référence T3", world.calculator(prices(S="10.000000")))
    copied = snapshot.parameters

    world.scenarios.put_parameter(
        "scn-etude", ScenarioParameter(part_ref="A", labour_minutes=Decimal("7")),
    )
    path_id = world.scenarios.parameter_ids("scn-etude")[("S", "V/B/S")]
    world.scenarios.delete_parameter("scn-etude", path_id)

    assert world.snapshots_repo.get(snapshot.id).parameters == copied


def test_a_blank_name_is_refused_before_anything_runs(world):
    with pytest.raises(InvalidSnapshotName):
        world.freeze("   ", world.calculator(prices(S="10.000000")))

    assert world.calls == []
    assert len(world.calculations.order) == 0
    assert tuple(world.snapshots_repo.list_for("bom-test")) == ()


def test_a_name_already_used_in_the_version_is_refused_whatever_case_or_accents(
    world,
):
    calculate = world.calculator(prices(S="10.000000"))
    first = world.freeze("Référence T3", calculate, snapshot_id="csn-1")

    with pytest.raises(SnapshotNameTaken) as refused:
        world.freeze("reference t3", calculate, snapshot_id="csn-2")

    assert refused.value.existing_id == first.id
    assert len(world.calls) == 1
    assert [s.id for s in world.snapshots_repo.list_for("bom-test")] == ["csn-1"]


def test_a_non_validated_version_cannot_be_frozen(diamond):
    world = World(diamond, validated=False)
    world.scenarios.create(study())

    with pytest.raises(BomVersionNotValidated):
        world.freeze("Référence T3", world.calculator(prices(S="10.000000")))

    assert world.calls == []
    assert len(world.calculations.order) == 0
    assert tuple(world.snapshots_repo.list_for("bom-test")) == ()


def test_an_incomplete_calculation_can_be_frozen_and_keeps_its_status(world):
    snapshot = world.freeze("Sans prix", world.calculator(prices("snp-vide")))

    calculation = world.calculations.get(snapshot.calculation_id)
    assert calculation.status is CalculationStatus.INCOMPLETE
    assert world.snapshots_repo.get(snapshot.id).calculation_id == calculation.id


def test_renaming_changes_the_name_and_keeps_the_history(world):
    before = world.freeze(
        "Initial", world.calculator(prices(S="10.000000")), now=NOW,
    )

    renamed = rename_snapshot(
        before.id, "Nouveau", snapshots_repo=world.snapshots_repo, now=LATER,
    )

    assert renamed.name == "Nouveau"
    assert world.snapshots_repo.get(before.id).name == "Nouveau"
    assert list(world.snapshots_repo.name_history(before.id)) == [
        ("Initial", NOW), ("Nouveau", LATER),
    ]
    assert replace(world.snapshots_repo.get(before.id), name="Initial") == before


def test_renaming_to_a_name_taken_by_another_snapshot_is_refused(world):
    calculate = world.calculator(prices(S="10.000000"))
    first = world.freeze("A", calculate, snapshot_id="csn-1")
    second = world.freeze("B", calculate, snapshot_id="csn-2")

    with pytest.raises(SnapshotNameTaken) as refused:
        rename_snapshot(
            second.id, "a", snapshots_repo=world.snapshots_repo, now=LATER,
        )

    assert refused.value.existing_id == first.id
    assert world.snapshots_repo.get(second.id).name == "B"
    assert list(world.snapshots_repo.name_history(second.id)) == [("B", NOW)]


def test_renaming_to_a_blank_name_is_refused(world):
    snapshot = world.freeze("Initial", world.calculator(prices(S="10.000000")))

    with pytest.raises(InvalidSnapshotName):
        rename_snapshot(
            snapshot.id, "  ", snapshots_repo=world.snapshots_repo, now=LATER,
        )

    assert world.snapshots_repo.get(snapshot.id).name == "Initial"


def test_renaming_to_its_own_name_with_other_case_is_allowed(world):
    snapshot = world.freeze("Initial", world.calculator(prices(S="10.000000")))

    renamed = rename_snapshot(
        snapshot.id, "INITIAL", snapshots_repo=world.snapshots_repo, now=LATER,
    )

    assert renamed.name == "INITIAL"
    assert world.snapshots_repo.get(snapshot.id).name == "INITIAL"


def test_two_snapshots_compare_without_recalculating(world):
    calculate = world.calculator(prices(S="10.000000"))
    italy = world.freeze("Fournisseur italien", calculate, snapshot_id="csn-1")
    manage_scenarios.put_parameter(
        "scn-etude", ScenarioParameter(part_ref="S", supplier_id="SUP-DE"),
        world.boms, world.scenarios, world.sourcing,
    )
    germany = world.freeze("Fournisseur allemand", calculate, snapshot_id="csn-2")
    frozen_a = world.calculations.get(italy.calculation_id)
    frozen_b = world.calculations.get(germany.calculation_id)
    calculations_before = list(world.calculations.order)

    comparison, a, b = compare_snapshots(
        italy.id, germany.id,
        snapshots_repo=world.snapshots_repo, calculations=world.calculations,
    )

    assert frozen_a.total_cost != frozen_b.total_cost
    assert comparison.total_a == frozen_a.total_cost
    assert comparison.total_b == frozen_b.total_cost
    assert (a.name, b.name) == ("Fournisseur italien", "Fournisseur allemand")
    assert world.calculations.order == calculations_before
    assert len(world.calls) == 2


def test_snapshots_on_different_price_snapshots_are_refused(world):
    first = world.freeze(
        "Prix de septembre", world.calculator(prices("snp-sept", S="10.000000")),
        snapshot_id="csn-1",
    )
    second = world.freeze(
        "Prix d'octobre", world.calculator(prices("snp-oct", S="11.000000")),
        snapshot_id="csn-2",
    )

    with pytest.raises(IncomparableCalculations):
        compare_snapshots(
            first.id, second.id,
            snapshots_repo=world.snapshots_repo, calculations=world.calculations,
        )


def test_an_unknown_snapshot_is_reported(world):
    known = world.freeze("Référence T3", world.calculator(prices(S="10.000000")))

    with pytest.raises(CalculationSnapshotNotFound):
        world.snapshots_repo.get("csn-inconnu")
    with pytest.raises(CalculationSnapshotNotFound):
        compare_snapshots(
            "csn-inconnu", known.id,
            snapshots_repo=world.snapshots_repo, calculations=world.calculations,
        )


def test_a_scenario_freezes_with_no_origin_by_default(world):
    snapshot = world.freeze("Référence T3", world.calculator(prices(S="10.000000")))

    assert snapshot.derived_from is None


def test_freezing_a_derived_scenario_copies_the_snapshot_it_came_from(diamond):
    world = World(diamond)
    manage_scenarios.create_scenario(
        study(derived_from="csn-origine"), world.boms, world.scenarios,
        world.sourcing,
    )

    snapshot = world.freeze("Reprise", world.calculator(prices(S="10.000000")))

    assert snapshot.derived_from == "csn-origine"
    assert world.snapshots_repo.get(snapshot.id).derived_from == "csn-origine"
