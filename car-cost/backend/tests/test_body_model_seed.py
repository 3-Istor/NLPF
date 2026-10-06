"""La maquette générée du Multipla (ADR-0017 §5), mesurée par le lecteur glTF.

Chaque pièce de carrosserie à matière déclarée y est un pavé dont la masse
mesurée vaut exactement la quantité de son arête vers la matière (R1).
"""

import hashlib
import math
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from carcost.infrastructure.gltf_reader import read_glb
from carcost.infrastructure.seed_loader import build_load_script, read_seeds, seed_bom

SEEDS = Path(__file__).resolve().parents[2] / "seeds"
MOCKUP = SEEDS / "body_multipla.glb"


def body_pieces():
    """{ref: quantité cumulée sous CAR-ASSY} des pièces fabriquées à matière."""
    bom = seed_bom(SEEDS)
    cumulative = Counter()

    def walk(ref, quantity):
        cumulative[ref] += quantity
        for child, per_unit in bom.children_of(ref):
            walk(child, quantity * per_unit)

    walk("CAR-ASSY", Decimal(1))
    return bom, {
        ref: quantity
        for ref, quantity in cumulative.items()
        if bom.parts[ref].material_ref and not bom.parts[ref].is_purchased
    }


def pieces_of(model):
    return [obj for obj in model.objects if obj.spec is not None]


def measured_mass(volume: Fraction, density: Decimal) -> Decimal:
    """arrondi₁₀⁻⁶(volume × densité), ROUND_HALF_UP, sans passer par un float."""
    micro = math.floor(volume * Fraction(density) * 10**6 + Fraction(1, 2))
    return Decimal(micro) / Decimal(10**6)


def test_the_mockup_has_one_object_per_mounted_body_piece():
    model = read_glb(MOCKUP.read_bytes())
    _, expected = body_pieces()

    counts = Counter(obj.spec["ref"] for obj in pieces_of(model))

    assert len(pieces_of(model)) == 51
    assert len(counts) == 26
    assert set(counts) == set(expected)
    assert {ref: Decimal(n) for ref, n in counts.items()} == expected


def test_each_measured_mass_equals_the_material_quantity():
    model = read_glb(MOCKUP.read_bytes())
    bom, expected = body_pieces()
    masses = {}
    for obj in pieces_of(model):
        part = bom.parts[obj.spec["ref"]]
        density = bom.parts[part.material_ref].density_kg_m3
        masses[part.ref] = measured_mass(obj.volume_m3, density)

    for ref in expected:
        material = bom.parts[ref].material_ref
        quantity = dict(bom.children_of(ref))[material]
        assert masses[ref] == quantity, ref
    assert masses["INT-DOOR-PANEL-FRONT"] == Decimal("1.600000")


def test_occurrences_share_one_mesh_and_are_closed():
    model = read_glb(MOCKUP.read_bytes())
    meshes = {}
    for obj in pieces_of(model):
        meshes.setdefault(obj.spec["ref"], set()).add(obj.mesh_index)

    assert all(len(indexes) == 1 for indexes in meshes.values()), meshes
    assert all(obj.is_closed and obj.volume_m3 > 0 for obj in pieces_of(model))


def test_decor_is_present_and_ignored():
    model = read_glb(MOCKUP.read_bytes())

    assert sum(1 for obj in model.objects if obj.spec is None) >= 3


def test_the_load_script_attaches_the_mockup():
    digest = hashlib.sha256(MOCKUP.read_bytes()).hexdigest()

    multipla = build_load_script(**read_seeds(SEEDS))
    valhalla = build_load_script(**read_seeds(SEEDS / "valhalla" / "hybride"))

    assert "INSERT INTO bom_model" in multipla
    assert digest in multipla
    assert "bom_model" not in valhalla
