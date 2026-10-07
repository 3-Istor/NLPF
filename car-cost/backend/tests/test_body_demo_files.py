"""Les fichiers de démonstration `seeds/demo/`, dérivés de la maquette (ADR-0017 §4.8).

Chacun passe par le vrai lecteur et le vrai cas d'usage d'import, sur la vraie
nomenclature et le snapshot fixe : les valeurs de contrôle y sont exactes.
Données synthétiques : maquette, densités et prix ne viennent d'aucun constructeur.
"""

from datetime import timedelta
from decimal import Decimal
from hashlib import sha256

import pytest

from carcost.application.body_import import BodyImportRejected
from carcost.application.import_body import import_body
from carcost.application.ports import StoredModel
from carcost.infrastructure.gltf_reader import read_glb
from fakes import (
    FakeBodyModelRepository, FakeBomVersions, FakeCalculationRepository, FakeScenarioRepository,
    FakeSnapshotRepository, FakeSourcingRepository, FakeVariantWriter,
)
from real_multipla import (
    MULTIPLA, SEEDS, TAKEN_AT, mockup_bytes, multipla_bom, multipla_sourcing, multipla_summary,
    reference_snapshot,
)

HOOD = "CAR-HOOD-SHELL"
NOW = TAKEN_AT + timedelta(hours=1)

DEMO = SEEDS / "demo"
ALU = "MAT-ALU-SHEET"
STEEL = "MAT-STEEL-SHEET"


class World:
    """Les dépôts en mémoire autour du Multipla, de sa maquette et de son snapshot fixe."""

    def __init__(self):
        self.boms = FakeBomVersions((multipla_summary(), multipla_bom()))
        glb = mockup_bytes()
        self.models = FakeBodyModelRepository(StoredModel(MULTIPLA, glb, sha256(glb).hexdigest(), "generated"))
        self.variants = FakeVariantWriter(self.boms, self.models, NOW)
        self.calculations = FakeCalculationRepository()

    def run(self, data):
        return import_body(
            MULTIPLA, data, read_model=read_glb, boms=self.boms, models=self.models,
            variants=self.variants, sourcing=FakeSourcingRepository(multipla_sourcing()),
            snapshots=FakeSnapshotRepository(reference_snapshot()), scenarios=FakeScenarioRepository(),
            calculations=self.calculations, clock=lambda: NOW, new_id=lambda: "0001",
        )


@pytest.fixture
def world():
    return World()


def demo(name):
    return (DEMO / name).read_bytes()


def test_aluminium_hood_file(world):
    outcome = world.run(demo("capot-alu.glb"))

    assert outcome.status == "CREATED"
    assert outcome.cost.delta == Decimal("-1.333147507383")
    [hood] = outcome.changes
    assert (hood.part_ref, hood.mass_before_kg, hood.mass_after_kg) == (HOOD, Decimal("11.2"), Decimal("3.852229"))


def test_spoiler_file(world):
    outcome = world.run(demo("aileron.glb"))

    assert outcome.status == "CREATED"
    assert outcome.cost.delta == Decimal("6.5233862")
    [calculation] = world.calculations.calculations.values()
    assert calculation.lines_by_ref["FIX-M8-20"].cumulative_quantity == 208


def test_surface_hood_file_is_refused(world):
    model = read_glb(demo("capot-surface.glb"))
    [hood] = [obj for obj in model.objects if obj.spec and obj.spec["ref"] == HOOD]

    with pytest.raises(BodyImportRejected) as caught:
        world.run(demo("capot-surface.glb"))

    [fault] = caught.value.faults
    assert (fault.code, fault.part_ref, fault.object_name) == ("MESH_NOT_CLOSED", HOOD, hood.name)


def test_mockup_file_changes_nothing(world):
    outcome = world.run(mockup_bytes())

    assert outcome.status == "NO_CHANGE"
    assert outcome.cost.delta == 0


def test_aluminium_body_file(world):
    outcome = world.run(demo("carrosserie-alu.glb"))

    assert outcome.status == "CREATED"
    assert [
        (c.part_ref, c.kind, c.material_before, c.material_after, c.mass_before_kg, c.mass_after_kg)
        for c in outcome.changes
    ] == [
        (ref, "MODIFIED", STEEL, ALU, Decimal(before), Decimal(after))
        for ref, before, after in (
            ("CAR-DOOR-SHELL-FRONT", "9.4", "3.233121"),
            ("CAR-DOOR-SHELL-REAR", "8.6", "2.957962"),
            ("CAR-HOOD-SHELL", "11.2", "3.852229"),
            ("CAR-PANEL-ROOF", "12.4", "4.264968"),
            ("CAR-TAILGATE-SHELL", "10.4", "3.577070"),
        )
    ]
    assert [c.mass_delta_kg for c in outcome.changes] == [
        Decimal(d) for d in ("-6.166879", "-5.642038", "-7.347771", "-8.135032", "-6.822930")
    ]
    [calculation] = world.calculations.calculations.values()
    assert calculation.lines_by_ref[STEEL].cumulative_quantity == Decimal("227.3")
    assert calculation.lines_by_ref[ALU].cumulative_quantity == Decimal("28.076433")


def volumes(name_or_bytes):
    data = name_or_bytes if isinstance(name_or_bytes, bytes) else demo(name_or_bytes)
    return {obj.name: obj.volume_m3 for obj in read_glb(data).objects}


def test_aluminium_body_keeps_the_same_geometry():
    mockup, body = volumes(mockup_bytes()), volumes("carrosserie-alu.glb")

    assert body == mockup
    assert len([n for n in body if n.split(" ")[0] in {
        "CAR-HOOD-SHELL", "CAR-PANEL-ROOF", "CAR-DOOR-SHELL-FRONT", "CAR-DOOR-SHELL-REAR", "CAR-TAILGATE-SHELL"}]) == 7


def test_aluminium_hood_keeps_the_same_geometry():
    assert volumes("capot-alu.glb") == volumes(mockup_bytes())
