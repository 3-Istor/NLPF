"""Import d'une variante de carrosserie, chiffrée en euros (ADR-0017 §6, §8, §9).

Vraie nomenclature du Multipla, vraies offres par défaut, prix de référence
figés, 42 €/h : les valeurs de contrôle du plan y sont vérifiées au centime
près, et bien au-delà. Prix, densités et maquette sont synthétiques.
"""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256

import pytest

from carcost.application.body_import import BodyImportRejected, plan_variant
from carcost.application.body_model import BodyModel, ModelObject
from carcost.application.compare_scenarios import IncomparableCalculations, compare_calculations
from carcost.application.import_body import body_changes, import_body, price_origin
from carcost.application.ports import BomVersionNotFound, ModelNotFound, StoredModel, VariantIdCollision
from carcost.application.import_body import IncompletePrices
from carcost.application.run_calculation import CalculationStatus
from carcost.application.price_resolution import resolve_unit_prices
from carcost.application.run_calculation import run_calculation
from carcost.application.scenario import Scenario
from carcost.infrastructure.gltf_reader import read_glb
from fakes import (
    FakeBodyModelRepository,
    FakeBomVersions,
    FakeCalculationRepository,
    FakeScenarioRepository,
    FakeSnapshotRepository,
    FakeSourcingRepository,
    FakeVariantWriter,
)
from gltf_builder import f32
from real_multipla import (
    MULTIPLA,
    TAKEN_AT,
    mockup_bytes,
    multipla_bom,
    multipla_sourcing,
    multipla_summary,
    reference_snapshot,
)

NOW = TAKEN_AT + timedelta(hours=1)
HOOD = "CAR-HOOD-SHELL"


def spoiler(**changes):
    obj = ModelObject(
        node_index=1000, name="Aileron", mesh_index=1000, materials=("MAT-ABS-GRANULE",),
        spec={"ref": "BODY-SPOILER", "parts": {"FIX-M8-20": "4"}},
        volume_m3=Fraction(f32(1.2)) * Fraction(0.25) * Fraction(f32(0.01)), is_closed=True,
    )
    return replace(obj, **changes)


def edited(model, ref, **changes):
    return BodyModel(tuple(
        replace(obj, **changes) if obj.spec and obj.spec["ref"] == ref else obj
        for obj in model.objects
    ))


@pytest.fixture(scope="module")
def static():
    """Ce qui ne bouge pas d'un test à l'autre, lu une fois."""
    mockup = read_glb(mockup_bytes())
    hood = edited(mockup, HOOD, materials=("MAT-ALU-SHEET",))
    return {
        "bom": multipla_bom(),
        "summary": multipla_summary(),
        "sourcing": multipla_sourcing(),
        "models": {
            b"capot-alu": hood,
            b"aileron": BodyModel(mockup.objects + (spoiler(),)),
            b"capot-alu+aileron": BodyModel(hood.objects + (spoiler(),)),
            b"fautif": BodyModel(
                edited(mockup, HOOD, materials=("MAT-UNOBTAINIUM",)).objects
                + (spoiler(spec={"ref": "BODY-SPOILER", "parts": {"FIX-NOPE": "1"}}),)
            ),
        },
    }


class World:
    """Les dépôts en mémoire autour du Multipla et de sa maquette."""

    def __init__(self, static, *, priced=True, modelled=True):
        self.boms = FakeBomVersions((static["summary"], static["bom"]))
        glb = mockup_bytes()
        self.models = FakeBodyModelRepository(
            *([StoredModel(MULTIPLA, glb, sha256(glb).hexdigest(), "generated")] if modelled else [])
        )
        self.variants = FakeVariantWriter(self.boms, self.models, NOW)
        self.sourcing = FakeSourcingRepository(static["sourcing"])
        self.snapshots = FakeSnapshotRepository(*([reference_snapshot()] if priced else []))
        self.scenarios = FakeScenarioRepository()
        self.calculations = FakeCalculationRepository()
        self.derived = static["models"]
        self.read = []
        self._ids = iter(range(1000))

    def read_model(self, data):
        self.read.append(data)
        return self.derived[data] if data in self.derived else read_glb(data)

    def run(self, data, version=MULTIPLA):
        return import_body(
            version, data, read_model=self.read_model, boms=self.boms, models=self.models,
            variants=self.variants, sourcing=self.sourcing, snapshots=self.snapshots,
            scenarios=self.scenarios, calculations=self.calculations,
            clock=lambda: NOW, new_id=lambda: f"{next(self._ids):04d}",
        )

    def changes_of(self, version):
        return body_changes(
            version, boms=self.boms, sourcing=self.sourcing, snapshots=self.snapshots, clock=lambda: NOW,
        )

    def writes(self):
        return len(self.variants.saved), len(self.scenarios.scenarios), len(self.calculations.calculations)


def variant_id(data, version=MULTIPLA):
    return f"{version}+{sha256(data).hexdigest()[:8]}"


@pytest.fixture
def world(static):
    return World(static)


def test_aluminium_hood_costs_less(world):
    outcome = world.run(b"capot-alu")

    assert outcome.status == "CREATED"
    assert outcome.cost_status == "OK"
    assert outcome.cost.snapshot_id == reference_snapshot().id
    assert outcome.cost.delta == Decimal("-1.333147507383")
    assert outcome.cost.total_before == Decimal("13285.661001170000")
    assert outcome.cost.total_after == Decimal("13284.327853662617")
    [hood] = outcome.changes
    assert (hood.part_ref, hood.mass_before_kg, hood.mass_after_kg) == (HOOD, Decimal("11.2"), Decimal("3.852229"))

    [variant] = world.variants.saved
    assert variant.id == outcome.variant_id == variant_id(b"capot-alu")
    assert variant.parent_id == MULTIPLA
    assert variant.label == outcome.variant_label == f"Fiat Multipla 1.6 16V — variante {variant_id(b'capot-alu')[-8:]}"
    assert variant.sha256 == sha256(b"capot-alu").hexdigest()
    assert variant.glb == b"capot-alu"
    assert variant.generator_version == "body-import/1"
    [scenario] = world.scenarios.scenarios.values()
    assert scenario.id == outcome.scenario_id
    assert (scenario.bom_version, scenario.display_currency, scenario.labour_rate, scenario.parameters) == (
        variant.id, "EUR", Decimal("42.00"), (),
    )
    assert scenario.name == f"Import — {variant.label}"
    [calculation] = world.calculations.calculations.values()
    assert (calculation.scenario_id, calculation.bom_version) == (scenario.id, variant.id)
    assert calculation.total_cost == outcome.cost.total_after


def test_spoiler_adds_its_material_and_fixings(world):
    outcome = world.run(b"aileron")

    assert outcome.status == "CREATED"
    assert outcome.cost.delta == Decimal("6.5233862")
    assert outcome.cost.total_after == Decimal("13292.18438737")
    [calculation] = world.calculations.calculations.values()
    assert calculation.lines_by_ref["FIX-M8-20"].cumulative_quantity == 208


def test_reimported_mockup_changes_nothing(world):
    outcome = world.run(mockup_bytes())

    assert outcome.status == "NO_CHANGE"
    assert (outcome.variant_id, outcome.variant_label, outcome.scenario_id, outcome.changes) == (None, None, None, ())
    assert outcome.cost.delta == 0
    assert outcome.cost.total_before == outcome.cost.total_after == Decimal("13285.661001170000")
    assert world.writes() == (0, 0, 0)


def test_same_file_twice_is_already_imported(world):
    first = world.run(b"aileron")
    second = world.run(b"aileron")

    assert second.status == "ALREADY_IMPORTED"
    assert (second.variant_id, second.variant_label) == (first.variant_id, first.variant_label)
    assert second.scenario_id is None
    assert second.changes == first.changes
    assert second.cost.delta == first.cost.delta == Decimal("6.5233862")
    assert world.writes() == (1, 1, 1)


def test_id_collision_is_refused(world, static):
    taken = variant_id(b"aileron")
    world.boms.entries[taken] = (replace(static["summary"], id=taken, parent_version_id=MULTIPLA), static["bom"])
    world.models.models[taken] = StoredModel(taken, b"autre", "0" * 64, "imported")

    with pytest.raises(VariantIdCollision):
        world.run(b"aileron")
    assert world.writes() == (0, 0, 0)


def test_without_price_snapshot_the_variant_exists_but_is_not_priced(static):
    world = World(static, priced=False)

    outcome = world.run(b"capot-alu")

    assert outcome.status == "CREATED"
    assert outcome.cost is None
    assert outcome.cost_status == "NO_PRICES"
    assert world.writes() == (1, 1, 0)


def test_reimport_without_price_snapshot_is_not_priced_either(static):
    world = World(static, priced=False)

    outcome = world.run(mockup_bytes())

    assert (outcome.status, outcome.cost, outcome.cost_status) == ("NO_CHANGE", None, "NO_PRICES")


def test_rejected_import_writes_nothing(world):
    with pytest.raises(BodyImportRejected) as caught:
        world.run(b"fautif")

    assert sorted(f.code for f in caught.value.faults) == ["UNKNOWN_MATERIAL", "UNKNOWN_PART"]
    assert world.writes() == (0, 0, 0)


def test_version_without_model_is_refused(static):
    world = World(static, modelled=False)

    with pytest.raises(ModelNotFound):
        world.run(b"capot-alu")
    assert world.read == []
    assert world.writes() == (0, 0, 0)


def test_unknown_version_is_refused(world):
    with pytest.raises(BomVersionNotFound):
        world.run(b"capot-alu", version="bom-inconnue")
    assert world.read == []


def test_a_variant_of_a_variant_is_priced_on_the_origin_snapshot(world):
    hood = world.run(b"capot-alu")

    outcome = world.run(b"capot-alu+aileron", version=hood.variant_id)

    assert outcome.status == "CREATED"
    assert outcome.parent_version == hood.variant_id
    assert price_origin(outcome.variant_id, world.boms) == MULTIPLA
    assert outcome.cost.snapshot_id == reference_snapshot().id
    assert outcome.cost.delta == Decimal("6.5233862")
    assert outcome.cost.total_before == Decimal("13284.327853662617")
    assert [c.part_ref for c in outcome.changes] == ["BODY-SPOILER"]


def test_body_changes_of_a_variant(world):
    hood = world.run(b"capot-alu")
    before = world.writes()

    changes = world.changes_of(hood.variant_id)

    assert changes.version == hood.variant_id
    assert changes.parent_version == MULTIPLA
    assert changes.changes == hood.changes
    assert len(changes.changes) == 1
    assert changes.cost.delta == Decimal("-1.333147507383")
    assert changes.cost_status == "OK"
    assert world.writes() == before

    origin = world.changes_of(MULTIPLA)
    assert (origin.parent_version, origin.changes, origin.cost, origin.cost_status) == (None, (), None, "OK")


def test_body_changes_without_price_snapshot(static):
    world = World(static)
    hood = world.run(b"capot-alu")
    world.snapshots.snapshots.clear()

    changes = world.changes_of(hood.variant_id)

    assert (changes.cost, changes.cost_status) == (None, "NO_PRICES")
    assert len(changes.changes) == 1


def test_compare_calculations_accepts_two_versions_on_one_snapshot(world, static):
    snapshot = reference_snapshot()
    plan = plan_variant(static["bom"], static["models"][b"capot-alu"])

    def calculate(bom, version):
        scenario = Scenario(f"scn-{version}", version, "EUR", Decimal("42.00"))
        resolved = resolve_unit_prices(bom, static["sourcing"], snapshot, scenario)
        return run_calculation(
            bom=bom, scenario=scenario, snapshot=snapshot, resolved=resolved, now=NOW,
            calculation_id=f"calc-{version}",
        )

    a, b = calculate(static["bom"], MULTIPLA), calculate(plan.bom, "variante")

    assert compare_calculations(a, b).cost_delta == b.total_cost - a.total_cost == Decimal("-1.333147507383")
    with pytest.raises(IncomparableCalculations, match="même snapshot"):
        compare_calculations(a, replace(b, snapshot_id="autre"))


NO_PRICE = ("FIX-M8-20", "MAT-ALU-SHEET")


def without_prices(world, static):
    """Le snapshot de référence privé de deux prix, que le Multipla utilise."""
    snapshot = reference_snapshot()
    snapshot = replace(snapshot, prices={r: p for r, p in snapshot.prices.items() if r not in NO_PRICE})
    world.snapshots.snapshots[:] = [snapshot]
    scenario = Scenario("scn-pre", MULTIPLA, "EUR", Decimal("42.00"))
    calculation = run_calculation(
        bom=static["bom"], scenario=scenario, snapshot=snapshot, now=NOW, calculation_id="calc-pre",
        resolved=resolve_unit_prices(static["bom"], static["sourcing"], snapshot, scenario),
    )
    assert calculation.status is CalculationStatus.INCOMPLETE
    return snapshot


def test_import_on_incomplete_prices_is_refused_and_names_the_parts(world, static):
    snapshot = without_prices(world, static)

    with pytest.raises(IncompletePrices) as caught:
        world.run(b"capot-alu")

    assert caught.value.parts_without_price == NO_PRICE
    assert all(ref in str(caught.value) for ref in NO_PRICE)
    assert caught.value.snapshot_id == snapshot.id
    assert world.writes() == (0, 0, 0)


def test_reimport_on_incomplete_prices_is_refused_too(world, static):
    world.run(b"aileron")
    before = world.writes()
    snapshot = without_prices(world, static)

    for data in (mockup_bytes(), b"aileron"):
        with pytest.raises(IncompletePrices) as caught:
            world.run(data)
        assert caught.value.parts_without_price == NO_PRICE
        assert caught.value.snapshot_id == snapshot.id
    assert world.writes() == before == (1, 1, 1)


def test_body_changes_on_incomplete_prices_names_the_parts(world, static):
    hood = world.run(b"capot-alu")
    before = world.writes()
    without_prices(world, static)

    with pytest.raises(IncompletePrices) as caught:
        world.changes_of(hood.variant_id)

    assert caught.value.parts_without_price == NO_PRICE
    assert world.writes() == before
