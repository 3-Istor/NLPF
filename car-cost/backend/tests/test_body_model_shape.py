"""La maquette du Multipla a une silhouette de voiture (voiture-jouet stylisée).

Lu en bibliothèque standard. Boîte englobante monde d'un nœud = `min`/`max` de
l'accessor POSITION + translation : la maquette ne pose rien autrement.
"""

import json
import struct
from pathlib import Path

from carcost.infrastructure.seed_loader import seed_bom

SEEDS = Path(__file__).resolve().parents[2] / "seeds"
SKIN = ("CAR-HOOD-SHELL", "CAR-PANEL-ROOF", "CAR-PANEL-SIDE", "CAR-DOOR-SHELL-FRONT",
        "CAR-DOOR-SHELL-REAR", "CAR-TAILGATE-SHELL", "CAR-BUMPER-SKIN-FRONT",
        "CAR-BUMPER-SKIN-REAR", "CAR-WHEEL-ARCH")


def load():
    data = (SEEDS / "body_multipla.glb").read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    return document, data[28 + json_length:]


def is_piece(node):
    return "carcost" in node.get("extras", {})


def materials(document, node):
    return {document["materials"][p["material"]]["name"]
            for p in document["meshes"][node["mesh"]]["primitives"]}


def box(document, node):
    """(min, max) monde du nœud."""
    assert not {"rotation", "scale", "matrix", "children"} & set(node), node["name"]
    t = node.get("translation", [0, 0, 0])
    lows, highs = [], []
    for primitive in document["meshes"][node["mesh"]]["primitives"]:
        accessor = document["accessors"][primitive["attributes"]["POSITION"]]
        lows.append([m + o for m, o in zip(accessor["min"], t)])
        highs.append([m + o for m, o in zip(accessor["max"], t)])
    return [min(c) for c in zip(*lows)], [max(c) for c in zip(*highs)]


def union(boxes):
    boxes = list(boxes)
    return ([min(b[0][i] for b in boxes) for i in range(3)],
            [max(b[1][i] for b in boxes) for i in range(3)])


def by_name(document):
    return {node["name"]: node for node in document["nodes"]}


def distinct_vertices(document, binary, mesh):
    seen = set()
    for primitive in document["meshes"][mesh]["primitives"]:
        accessor = document["accessors"][primitive["attributes"]["POSITION"]]
        view = document["bufferViews"][accessor["bufferView"]]
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        seen.update(struct.iter_unpack("<3f", binary[start:start + 12 * accessor["count"]]))
    return len(seen)


def test_skin_panels_are_not_plain_boxes():
    document, binary = load()
    nodes = by_name(document)

    for ref in SKIN:
        mesh = nodes[f"{ref} 1"]["mesh"]
        assert distinct_vertices(document, binary, mesh) > 8, ref


def test_overall_size_is_a_multipla():
    document, _ = load()

    low, high = union(box(document, node) for node in document["nodes"])

    assert 1.75 <= high[0] - low[0] <= 1.95
    assert 1.55 <= high[1] - low[1] <= 1.80
    assert 3.85 <= high[2] - low[2] <= 4.15
    assert low[1] >= 0


def test_windscreen_step():
    document, _ = load()
    nodes = by_name(document)
    hood = box(document, nodes["CAR-HOOD-SHELL 1"])
    windscreen = box(document, nodes["Pare-brise 1"])

    assert hood[1][1] <= windscreen[0][1] - 0.05
    for name in ("Optique haute 1", "Optique haute 2"):
        low, high = box(document, nodes[name])
        assert hood[1][1] < (low[1] + high[1]) / 2 < windscreen[0][1], name
    assert windscreen[1][2] < hood[1][2]


def test_decor_wheels_glass_and_lights():
    document, _ = load()
    decor = [node for node in document["nodes"] if not is_piece(node)]
    refs = set(seed_bom(SEEDS).parts)

    def named(prefix):
        return [node for node in decor if node["name"].startswith(prefix)]

    assert not [node["name"] for node in decor if node["name"].rsplit(" ", 1)[0] in refs]
    assert len(named("Pneu ")) >= 4 and len(named("Jante ")) >= 4
    assert not {n["mesh"] for n in named("Pneu ")} & {n["mesh"] for n in named("Jante ")}
    glass = [node for node in decor if any("GLASS" in m for m in materials(document, node))]
    assert len(glass) >= 3
    assert len(named("Optique ") + named("Feu ")) >= 4


def test_materials_have_colours_and_keep_material_names():
    document, _ = load()
    bom = seed_bom(SEEDS)

    for material in document["materials"]:
        colour = material["pbrMetallicRoughness"]["baseColorFactor"]
        if "GLASS" in material["name"]:
            assert material["alphaMode"] == "BLEND" and colour[3] < 1, material["name"]
    pieces = [node for node in document["nodes"] if is_piece(node)]
    assert all(node["extras"]["carcost"] == {"ref": node["name"].rsplit(" ", 1)[0]}
               for node in pieces)
    names = set().union(*(materials(document, node) for node in pieces))
    refs = {node["extras"]["carcost"]["ref"] for node in pieces}
    assert len(refs) == 26
    assert names == {bom.parts[ref].material_ref for ref in refs}


def test_pieces_stay_inside_the_body():
    document, _ = load()
    pieces = [node for node in document["nodes"] if is_piece(node)]
    painted = [node for node in pieces
               if "MAT-STEEL-SHEET" in materials(document, node)
               or node["extras"]["carcost"]["ref"].startswith("CAR-BUMPER-SKIN")]
    low, high = union(box(document, node) for node in painted)

    for node in pieces:
        node_low, node_high = box(document, node)
        assert all(a >= b - 0.02 for a, b in zip(node_low, low)), node["name"]
        assert all(a <= b + 0.02 for a, b in zip(node_high, high)), node["name"]


# ref → (axe de la largeur, axe du galbe, sens vers l'extérieur)
CROWNED = {
    "CAR-HOOD-SHELL": (0, 1, 1),
    "CAR-PANEL-ROOF": (0, 1, 1),
    "CAR-TAILGATE-SHELL": (0, 2, -1),
    "CAR-BUMPER-SKIN-FRONT": (1, 2, 1),
    "CAR-BUMPER-SKIN-REAR": (1, 2, -1),
}


def positions(document, binary, mesh):
    found = []
    for primitive in document["meshes"][mesh]["primitives"]:
        accessor = document["accessors"][primitive["attributes"]["POSITION"]]
        view = document["bufferViews"][accessor["bufferView"]]
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        found += struct.iter_unpack("<3f", binary[start:start + 12 * accessor["count"]])
    return found


def test_skin_panels_are_crowned_across_the_width():
    """Le milieu de la largeur dépasse les bords d'au moins 1 cm vers l'extérieur."""
    document, binary = load()
    nodes = by_name(document)

    for ref, (across, bulge, outward) in CROWNED.items():
        points = positions(document, binary, nodes[f"{ref} 1"]["mesh"])
        low = min(p[across] for p in points)
        high = max(p[across] for p in points)
        middle, half = (low + high) / 2, (high - low) / 2
        centre = max((outward * p[bulge] for p in points if abs(p[across] - middle) < 0.1 * half),
                     default=float("-inf"))  # aucun sommet au milieu : panneau plat
        edges = max(outward * p[bulge] for p in points if abs(p[across] - middle) > 0.9 * half)
        assert centre - edges >= 0.01, ref


def test_glass_is_dark_and_nearly_opaque():
    """Opacité ≥ 0,8 : ce qui est derrière une vitre y compte pour 20 % au plus,
    et pour 4 % au plus derrière deux vitres (de part et d'autre de la caisse)."""
    document, _ = load()

    glass = [m for m in document["materials"] if "GLASS" in m["name"]]
    assert glass
    for material in glass:
        *rgb, alpha = material["pbrMetallicRoughness"]["baseColorFactor"]
        assert 0.8 <= alpha < 1 and max(rgb) <= 0.2, material["name"]
