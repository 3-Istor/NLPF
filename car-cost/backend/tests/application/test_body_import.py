"""Règles d'import d'une variante de carrosserie (ADR-0017 §3, §6 et §11).

Toujours sur la vraie nomenclature du Multipla et sa maquette générée : les
valeurs de contrôle (capot alu 3,852229 kg, aileron 3,15 kg) en dépendent.
"""

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from carcost.application.body_import import (
    BodyImportRejected,
    NewPart,
    PartChange,
    diff_versions,
    measured_mass,
    plan_variant,
)
from carcost.application.body_model import BodyModel, ModelObject
from carcost.domain.bom_validation import validate_bom
from carcost.infrastructure.gltf_reader import read_glb
from carcost.infrastructure.seed_loader import seed_bom
from gltf_builder import f32

SEEDS = Path(__file__).resolve().parents[3] / "seeds"


@pytest.fixture(scope="module")
def parent():
    return seed_bom(SEEDS)


@pytest.fixture(scope="module")
def mockup():
    return read_glb((SEEDS / "body_multipla.glb").read_bytes())


def spoiler(node_index=1000, **changes):
    obj = ModelObject(
        node_index=node_index,
        name="Aileron",
        mesh_index=1000,
        materials=("MAT-ABS-GRANULE",),
        spec={"ref": "BODY-SPOILER", "parts": {"FIX-M8-20": "4"}},
        volume_m3=Fraction(f32(1.2)) * Fraction(0.25) * Fraction(f32(0.01)),
        is_closed=True,
    )
    return replace(obj, **changes)


def edited(mockup, ref, **changes):
    """La maquette, chaque objet de `ref` modifié par `changes`."""
    return BodyModel(
        tuple(
            replace(obj, **changes) if obj.spec and obj.spec["ref"] == ref else obj
            for obj in mockup.objects
        )
    )


def plus(mockup, *objects):
    return BodyModel(mockup.objects + objects)


def edge(bom, parent_ref, child_ref):
    return dict(bom.children_of(parent_ref)).get(child_ref)


def rejected(parent, model):
    with pytest.raises(BodyImportRejected) as caught:
        plan_variant(parent, model)
    return [(f.code, f.object_name, f.part_ref) for f in caught.value.faults]


def test_the_mockup_reimported_changes_nothing(parent, mockup):
    assert plan_variant(parent, mockup) is None


def test_aluminium_hood(parent, mockup):
    plan = plan_variant(parent, edited(mockup, "CAR-HOOD-SHELL", materials=("MAT-ALU-SHEET",)))

    assert validate_bom(plan.bom) == ()
    assert edge(plan.bom, "CAR-HOOD-SHELL", "MAT-ALU-SHEET") == Decimal("3.852229")
    assert edge(plan.bom, "CAR-HOOD-SHELL", "MAT-STEEL-SHEET") is None
    hood = plan.bom.parts["CAR-HOOD-SHELL"]
    assert hood.mass_kg == Decimal("3.852229")
    assert hood.material_ref == "MAT-ALU-SHEET"
    assert hood.labour_minutes == Decimal("16")
    assert plan.changes == (
        PartChange(
            "CAR-HOOD-SHELL", "Caisson de capot", "MODIFIED",
            "MAT-STEEL-SHEET", "MAT-ALU-SHEET", Decimal("11.2"), Decimal("3.852229"),
        ),
    )
    assert plan.changes[0].mass_delta_kg == Decimal("-7.347771")
    assert plan.updated_parts == {"CAR-HOOD-SHELL": ("MAT-ALU-SHEET", Decimal("3.852229"))}
    assert plan.new_parts == ()
    assert [e for e in plan.bom.edges if e.child_ref == "CAR-HOOD-SHELL"] == [
        e for e in parent.edges if e.child_ref == "CAR-HOOD-SHELL"
    ]
    assert plan.cumulative["CAR-HOOD-SHELL"] == 1
    assert plan.cumulative["FIX-M8-20"] == 204


def test_spoiler_is_a_new_part_under_the_body(parent, mockup):
    plan = plan_variant(parent, plus(mockup, spoiler()))

    assert validate_bom(plan.bom) == ()
    part = plan.bom.parts["BODY-SPOILER"]
    assert not part.is_purchased
    assert part.labour_minutes == 0
    assert part.mass_kg == Decimal("3.15")
    assert edge(plan.bom, "CAR-ASSY", "BODY-SPOILER") == 1
    assert edge(plan.bom, "BODY-SPOILER", "MAT-ABS-GRANULE") == Decimal("3.15")
    assert edge(plan.bom, "BODY-SPOILER", "FIX-M8-20") == 4
    assert plan.cumulative["FIX-M8-20"] == 208
    assert plan.new_parts == (
        NewPart(
            "BODY-SPOILER", "Aileron", "CAR", "body", "pce", "MAT-ABS-GRANULE",
            Decimal("3.15"), Decimal(0), Decimal(0),
        ),
    )
    assert plan.changes == (
        PartChange("BODY-SPOILER", "Aileron", "NEW", None, "MAT-ABS-GRANULE", None, Decimal("3.15")),
    )
    assert plan.changes[0].mass_delta_kg == Decimal("3.15")
    assert plan.updated_parts == {}


def test_a_new_part_without_a_name_is_labelled_by_its_ref(parent, mockup):
    plan = plan_variant(parent, plus(mockup, spoiler(name="")))

    assert plan.bom.parts["BODY-SPOILER"].label == "BODY-SPOILER"


def test_two_spoiler_objects_mean_two_mounted_spoilers(parent, mockup):
    plan = plan_variant(parent, plus(mockup, spoiler(1000), spoiler(1001)))

    assert edge(plan.bom, "CAR-ASSY", "BODY-SPOILER") == 2
    assert edge(plan.bom, "BODY-SPOILER", "MAT-ABS-GRANULE") == Decimal("3.15")
    assert plan.cumulative["FIX-M8-20"] == 212


def test_multi_material_piece_keeps_its_other_materials(parent, mockup):
    plan = plan_variant(
        parent, edited(mockup, "INT-DOOR-PANEL-FRONT", materials=("MAT-PP-GRANULE",))
    )
    volume = next(
        obj.volume_m3 for obj in mockup.objects
        if obj.spec and obj.spec["ref"] == "INT-DOOR-PANEL-FRONT"
    )

    measured = measured_mass(volume, Decimal("900"))
    assert plan.bom.parts["INT-DOOR-PANEL-FRONT"].mass_kg == Decimal("2.07") - Decimal("1.6") + measured
    assert edge(plan.bom, "INT-DOOR-PANEL-FRONT", "MAT-PP-GRANULE") == measured
    assert edge(plan.bom, "INT-DOOR-PANEL-FRONT", "MAT-ABS-GRANULE") is None
    for material in ("MAT-FABRIC-PES", "MAT-LEATHERETTE"):
        assert edge(plan.bom, "INT-DOOR-PANEL-FRONT", material) == edge(
            parent, "INT-DOOR-PANEL-FRONT", material
        )


def test_measured_mass_rounds_half_up_to_the_microgram():
    assert measured_mass(Fraction(1, 2_000_000), Decimal(1)) == Decimal("0.000001")
    assert measured_mass(Fraction(1, 3), Decimal(3)) == Decimal("1.000000")
    assert measured_mass(Fraction(2, 3), Decimal(1)) == Decimal("0.666667")


def test_a_model_without_carcost_objects_is_refused(parent, mockup):
    decor = BodyModel(tuple(obj for obj in mockup.objects if obj.spec is None))

    assert rejected(parent, decor) == [("INVALID_MODEL_FILE", None, None)]


def test_a_spec_without_ref_is_refused(parent, mockup):
    model = edited(mockup, "CAR-HOOD-SHELL", spec={})

    assert rejected(parent, model) == [("MISSING_SPEC", "CAR-HOOD-SHELL 1", None)]


def test_an_object_without_material_is_refused(parent, mockup):
    model = edited(mockup, "CAR-HOOD-SHELL", materials=())

    assert rejected(parent, model) == [("MISSING_SPEC", "CAR-HOOD-SHELL 1", "CAR-HOOD-SHELL")]


@pytest.mark.parametrize(
    "changes, part_ref",
    [
        ({"spec": {"ref": "body-x"}}, "body-x"),
        ({"spec": {"ref": "BODY-SPOILER", "parts": {"FIX-M8-20": "-1"}}}, "BODY-SPOILER"),
        ({"spec": {"ref": "BODY-SPOILER", "parts": {"FIX-M8-20": "beaucoup"}}}, "BODY-SPOILER"),
        ({"spec": {"ref": "BODY-SPOILER", "parts": ["FIX-M8-20"]}}, "BODY-SPOILER"),
        ({"materials": ("MAT-ABS-GRANULE", "MAT-PP-GRANULE")}, "BODY-SPOILER"),
    ],
    ids=["lowercase-ref", "negative-quantity", "not-a-number", "parts-not-an-object", "two-materials"],
)
def test_an_invalid_spec_is_refused(parent, mockup, changes, part_ref):
    model = plus(mockup, spoiler(**changes))

    assert rejected(parent, model) == [("INVALID_SPEC", "Aileron", part_ref)]


def test_an_open_mesh_is_refused(parent, mockup):
    model = edited(mockup, "CAR-HOOD-SHELL", is_closed=False)

    assert rejected(parent, model) == [("MESH_NOT_CLOSED", "CAR-HOOD-SHELL 1", "CAR-HOOD-SHELL")]


def test_an_inverted_mesh_is_refused(parent, mockup):
    hood = next(obj for obj in mockup.objects if obj.spec and obj.spec["ref"] == "CAR-HOOD-SHELL")
    model = edited(mockup, "CAR-HOOD-SHELL", volume_m3=-hood.volume_m3)

    assert rejected(parent, model) == [("NON_POSITIVE_VOLUME", "CAR-HOOD-SHELL 1", "CAR-HOOD-SHELL")]


def test_an_unknown_material_is_refused(parent, mockup):
    model = edited(mockup, "CAR-HOOD-SHELL", materials=("MAT-UNOBTAINIUM",))

    assert rejected(parent, model) == [("UNKNOWN_MATERIAL", "CAR-HOOD-SHELL 1", "CAR-HOOD-SHELL")]


def test_a_material_without_density_is_refused(parent, mockup):
    model = edited(mockup, "CAR-HOOD-SHELL", materials=("MAT-PAINT-BASE",))

    assert rejected(parent, model) == [
        ("MATERIAL_WITHOUT_DENSITY", "CAR-HOOD-SHELL 1", "CAR-HOOD-SHELL")
    ]


def test_an_unknown_fixation_is_refused(parent, mockup):
    model = plus(mockup, spoiler(spec={"ref": "BODY-SPOILER", "parts": {"FIX-NOPE": "1"}}))

    assert rejected(parent, model) == [("UNKNOWN_PART", "Aileron", "BODY-SPOILER")]


def test_a_manufactured_fixation_is_refused(parent, mockup):
    model = plus(mockup, spoiler(spec={"ref": "BODY-SPOILER", "parts": {"CAR-HOOD-ASSY": "1"}}))

    assert rejected(parent, model) == [("NOT_PURCHASED", "Aileron", "BODY-SPOILER")]


def test_the_ref_of_a_purchased_part_is_refused(parent, mockup):
    model = plus(mockup, spoiler(name="Charnière", spec={"ref": "CAR-DOOR-HINGE"}))

    assert rejected(parent, model) == [("REF_IS_PURCHASED", "Charnière", "CAR-DOOR-HINGE")]


def test_the_ref_of_an_assembly_without_material_is_refused(parent, mockup):
    model = plus(mockup, spoiler(name="Caisse", spec={"ref": "CAR-BIW-ASSY"}))

    assert rejected(parent, model) == [("NOT_A_MATERIAL_PIECE", "Caisse", "CAR-BIW-ASSY")]


def test_occurrences_on_different_meshes_are_refused(parent, mockup):
    model = BodyModel(
        tuple(
            replace(obj, mesh_index=999) if obj.name == "CAR-PANEL-SIDE 2" else obj
            for obj in mockup.objects
        )
    )

    assert rejected(parent, model) == [("OCCURRENCES_DIFFER", "CAR-PANEL-SIDE 2", "CAR-PANEL-SIDE")]


def test_occurrences_of_a_new_part_with_different_fixations_are_refused(parent, mockup):
    other = spoiler(1001, name="Aileron 2", spec={"ref": "BODY-SPOILER", "parts": {"FIX-M8-20": "2"}})
    model = plus(mockup, spoiler(), other)

    assert rejected(parent, model) == [("OCCURRENCES_DIFFER", "Aileron 2", "BODY-SPOILER")]


def test_all_faults_are_reported_together(parent, mockup):
    model = BodyModel(
        tuple(
            replace(obj, is_closed=False) if obj.name == "CAR-HOOD-SHELL 1"
            else replace(obj, materials=("MAT-UNOBTAINIUM",)) if obj.name == "CAR-PANEL-ROOF 1"
            else obj
            for obj in mockup.objects
        )
        + (spoiler(name="Charnière", spec={"ref": "CAR-DOOR-HINGE"}),)
    )

    assert rejected(parent, model) == [
        ("MESH_NOT_CLOSED", "CAR-HOOD-SHELL 1", "CAR-HOOD-SHELL"),
        ("UNKNOWN_MATERIAL", "CAR-PANEL-ROOF 1", "CAR-PANEL-ROOF"),
        ("REF_IS_PURCHASED", "Charnière", "CAR-DOOR-HINGE"),
    ]


def test_bom_violations_become_faults(parent, mockup):
    model = plus(mockup, spoiler(spec={"ref": "BODY-SPOILER", "parts": {"MAT-ABS-GRANULE": "1"}}))

    assert rejected(parent, model) == [("DUPLICATE_EDGE", None, "MAT-ABS-GRANULE")]


def test_diff_versions_matches_the_plan(parent, mockup):
    hood = plan_variant(parent, edited(mockup, "CAR-HOOD-SHELL", materials=("MAT-ALU-SHEET",)))
    wing = plan_variant(parent, plus(mockup, spoiler()))

    assert diff_versions(parent, hood.bom) == hood.changes
    assert diff_versions(parent, wing.bom) == wing.changes
    assert diff_versions(parent, parent) == ()
