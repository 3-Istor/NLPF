"""Lecteur glTF binaire (ADR-0017 §1 à §3) : volume exact, fermeture, refus."""

from __future__ import annotations

import json
import struct
from decimal import Decimal
from fractions import Fraction

import pytest

from carcost.application.body_model import ModelFileRejected
from carcost.infrastructure.gltf_reader import read_glb
from gltf_builder import box, f32, glb, model

BOX = box(1.2, 0.25, 0.01)
BOX_VOLUME = Fraction(f32(1.2)) * Fraction(0.25) * Fraction(f32(0.01))


def only(data: bytes):
    (obj,) = read_glb(data).objects
    return obj


def test_a_box_volume_is_exact():
    obj = only(model(*BOX))

    assert obj.volume_m3 == BOX_VOLUME
    volume = obj.volume_m3
    assert round(Decimal(volume.numerator) / volume.denominator, 9) == Decimal("0.003")
    assert obj.is_closed is True


def test_scale_is_applied():
    obj = only(model(*BOX, nodes=[{"mesh": 0, "scale": [2, 1, 1]}]))

    assert obj.volume_m3 == 2 * BOX_VOLUME


def test_translation_and_rotation_keep_the_volume():
    node = {
        "mesh": 0,
        "translation": [3, -1, 2],
        "rotation": [0, 0, 0.7071067811865476, 0.7071067811865476],
    }
    obj = only(model(*BOX, nodes=[node]))

    assert abs(obj.volume_m3 - BOX_VOLUME) < Fraction(1, 10**9)
    assert obj.is_closed is True


def test_parent_transform_is_composed():
    nodes = [{"scale": [1, 3, 1], "children": [1]}, {"mesh": 0}]
    obj = only(model(*BOX, nodes=nodes))

    assert obj.node_index == 1
    assert obj.volume_m3 == 3 * BOX_VOLUME


def test_two_nodes_share_one_mesh():
    nodes = [{"mesh": 0, "translation": [1, 0, 0]}, {"mesh": 0}]
    first, second = read_glb(model(*BOX, nodes=nodes)).objects

    assert (first.node_index, second.node_index) == (0, 1)
    assert first.mesh_index == second.mesh_index == 0
    assert first.volume_m3 == second.volume_m3 == BOX_VOLUME


def test_a_missing_face_is_not_closed():
    corners, triangles = BOX
    assert only(model(corners, triangles[:-2])).is_closed is False


def test_inverted_normals_give_a_negative_volume():
    corners, triangles = BOX
    obj = only(model(corners, [(a, c, b) for a, b, c in triangles]))

    assert obj.volume_m3 < 0


def test_unindexed_triangles_are_read():
    obj = only(model(*BOX, indexed=False))

    assert obj.volume_m3 == BOX_VOLUME
    assert obj.is_closed is True


def test_byte_stride_is_respected():
    obj = only(model(*BOX, stride=20))

    assert obj.volume_m3 == BOX_VOLUME


def test_extras_and_materials_are_exposed():
    spec = {"ref": "BODY-SPOILER", "parts": {"FIX-M8-20": "4"}}
    nodes = [{"mesh": 0, "name": "aileron", "extras": {"carcost": spec}}, {"mesh": 0}]
    part, decor = read_glb(model(*BOX, nodes=nodes, material="MAT-ABS-GRANULE")).objects

    assert part.name == "aileron"
    assert part.spec == spec
    assert part.materials == ("MAT-ABS-GRANULE",)
    assert decor.name == ""
    assert decor.spec is None


def test_draco_is_refused():
    data = model(*BOX, extensions_required=["KHR_draco_mesh_compression"])

    with pytest.raises(ModelFileRejected) as refused:
        read_glb(data)

    assert refused.value.code == "UNSUPPORTED_EXTENSION"
    assert "KHR_draco_mesh_compression" in refused.value.message


def with_version_1(data: bytes) -> bytes:
    return data[:4] + struct.pack("<I", 1) + data[8:]


def without_bin() -> bytes:
    text = json.dumps({"asset": {"version": "2.0"}}).encode()
    text += b" " * (-len(text) % 4)
    chunk = struct.pack("<II", len(text), 0x4E4F534A) + text
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunk)) + chunk


@pytest.mark.parametrize(
    "data",
    [
        b"",
        model(*BOX)[:20],
        b"gltf" + model(*BOX)[4:],
        with_version_1(model(*BOX)),
        glb(b"{not json", b"\0\0\0\0"),
        without_bin(),
    ],
    ids=["empty", "truncated", "bad-magic", "version-1", "bad-json", "no-bin"],
)
def test_garbage_is_refused(data):
    with pytest.raises(ModelFileRejected) as refused:
        read_glb(data)

    assert refused.value.code == "INVALID_MODEL_FILE"
