"""Lecteur glTF 2.0 binaire (.glb) en bibliothèque standard (ADR-0017 §1 à §3).

Le volume est calculé en `Fraction` de bout en bout : positions float32,
transformations décimales du JSON, produit mixte. Un `float` perdrait des
chiffres et « réimporter la maquette ne change rien » deviendrait faux.
Le lecteur ne juge pas les règles d'import : il ne refuse que l'illisible.
"""

from __future__ import annotations

import json
import struct
from collections import Counter
from decimal import Decimal
from fractions import Fraction

from carcost.application.body_model import BodyModel, ModelFileRejected, ModelObject

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
INDEX_FORMATS = {5121: "B", 5123: "H", 5125: "I"}


class _Invalid(Exception):
    pass


def read_glb(data: bytes) -> BodyModel:
    try:
        document, binary = _chunks(data)
        if document.get("extensionsRequired"):
            names = ", ".join(map(str, document["extensionsRequired"]))
            raise ModelFileRejected(
                "UNSUPPORTED_EXTENSION", f"extension non prise en charge : {names}"
            )
        return _read(document, binary)
    except _Invalid as error:
        raise ModelFileRejected("INVALID_MODEL_FILE", str(error)) from None
    except (KeyError, IndexError, TypeError, ValueError, AttributeError,
            ArithmeticError, struct.error, RecursionError) as error:
        raise ModelFileRejected(
            "INVALID_MODEL_FILE", f"glTF illisible : {type(error).__name__} {error}"
        ) from None


def _chunks(data: bytes) -> tuple[dict, bytes]:
    if len(data) < 12:
        raise _Invalid("fichier trop court pour un glTF binaire")
    magic, version, length = struct.unpack_from("<4sII", data)
    if magic != b"glTF":
        raise _Invalid("ce n'est pas un glTF binaire")
    if version != 2:
        raise _Invalid(f"glTF version {version}, seule la version 2 est lue")
    if length != len(data):
        raise _Invalid("longueur déclarée incohérente")
    chunks, offset = {}, 12
    while offset < length:
        size, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + size > length:
            raise _Invalid("bloc tronqué")
        chunks.setdefault(kind, data[offset:offset + size])
        offset += size
    if JSON_CHUNK not in chunks or BIN_CHUNK not in chunks:
        raise _Invalid("bloc JSON ou BIN manquant")
    try:
        document = json.loads(chunks[JSON_CHUNK], parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _Invalid(f"JSON illisible : {error}") from None
    if not isinstance(document, dict):
        raise _Invalid("le JSON n'est pas un objet")
    return document, chunks[BIN_CHUNK]


def _read(document: dict, binary: bytes) -> BodyModel:
    if any("uri" in buffer for buffer in document.get("buffers", [])):
        raise _Invalid("buffer externe non pris en charge")
    nodes = document.get("nodes", [])
    parents = {child: i for i, node in enumerate(nodes) for child in node.get("children", [])}
    materials = document.get("materials", [])
    meshes = {}  # mesh_index -> (positions, triangles, materials, is_closed)
    objects = []
    for index, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        mesh_index = node["mesh"]
        if mesh_index not in meshes:
            meshes[mesh_index] = _mesh(document, binary, mesh_index, materials)
        positions, triangles, names, closed = meshes[mesh_index]
        world = _world(nodes, parents, index)
        points = [_apply(world, p) for p in positions]
        volume = sum(
            (_triple(points[a], points[b], points[c]) for a, b, c in triangles), Fraction(0)
        ) / 6
        extras = node.get("extras")
        objects.append(ModelObject(
            node_index=index,
            name=node.get("name", ""),
            mesh_index=mesh_index,
            materials=names,
            spec=extras.get("carcost") if isinstance(extras, dict) else None,
            volume_m3=volume,
            is_closed=closed,
        ))
    return BodyModel(tuple(objects))


def _mesh(document, binary, mesh_index, materials):
    """Positions distinctes (triplets float32 exacts), triangles en indices de
    ces positions, matériaux, fermeture."""
    slots, triangles, names = {}, [], set()
    for primitive in document["meshes"][mesh_index]["primitives"]:
        if primitive.get("mode", 4) != 4:
            raise _Invalid(f"primitive en mode {primitive['mode']}, seuls les triangles sont lus")
        if "material" in primitive:
            names.add(materials[primitive["material"]].get("name", ""))
        accessor = document["accessors"][primitive["attributes"]["POSITION"]]
        if accessor.get("componentType") != 5126 or accessor.get("type") != "VEC3":
            raise _Invalid("POSITION doit être en FLOAT VEC3")
        vertices = [slots.setdefault(p, len(slots)) for p in
                    _read_accessor(document, binary, accessor, "3f", 12)]
        if "indices" in primitive:
            accessor = document["accessors"][primitive["indices"]]
            if accessor.get("type") != "SCALAR" or accessor.get("componentType") not in INDEX_FORMATS:
                raise _Invalid("indices doivent être des entiers non signés SCALAR")
            fmt = INDEX_FORMATS[accessor["componentType"]]
            order = [i for (i,) in _read_accessor(document, binary, accessor, fmt,
                                                   struct.calcsize(fmt))]
        else:
            order = list(range(len(vertices)))
        if len(order) % 3:
            raise _Invalid("nombre de sommets non multiple de 3")
        triangles += [tuple(vertices[i] for i in order[k:k + 3]) for k in range(0, len(order), 3)]
    positions = [tuple(map(Fraction, p)) for p in slots]
    edges = Counter(frozenset(pair) for a, b, c in triangles for pair in ((a, b), (b, c), (c, a)))
    closed = bool(edges) and all(count == 2 for count in edges.values())
    return positions, triangles, tuple(sorted(names)), closed


def _read_accessor(document, binary, accessor, fmt, size):
    if "sparse" in accessor:
        raise _Invalid("accessor sparse non pris en charge")
    view = document["bufferViews"][accessor["bufferView"]]
    if view.get("buffer", 0) != 0:
        raise _Invalid("seul le buffer du bloc BIN est lu")
    stride = view.get("byteStride", size)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return [struct.unpack_from("<" + fmt, binary, start + k * stride)
            for k in range(accessor["count"])]


def _world(nodes, parents, index):
    matrix = _local(nodes[index])
    while index in parents:
        index = parents[index]
        matrix = _multiply(_local(nodes[index]), matrix)
    return matrix


def _local(node):
    """Matrice 4×4 exacte du nœud (lignes), depuis `matrix` ou T·R·S."""
    if "matrix" in node:
        m = [Fraction(v) for v in node["matrix"]]  # colonne par colonne
        return [[m[col * 4 + row] for col in range(4)] for row in range(4)]
    tx, ty, tz = map(Fraction, node.get("translation", [0, 0, 0]))
    x, y, z, w = map(Fraction, node.get("rotation", [0, 0, 0, 1]))
    sx, sy, sz = map(Fraction, node.get("scale", [1, 1, 1]))
    rotation = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    return [
        [rotation[r][0] * sx, rotation[r][1] * sy, rotation[r][2] * sz, t]
        for r, t in enumerate((tx, ty, tz))
    ] + [[Fraction(0), Fraction(0), Fraction(0), Fraction(1)]]


def _multiply(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _apply(m, p):
    return tuple(m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3))


def _triple(p1, p2, p3):
    """p1 · (p2 × p3)."""
    return (p1[0] * (p2[1] * p3[2] - p2[2] * p3[1])
            + p1[1] * (p2[2] * p3[0] - p2[0] * p3[2])
            + p1[2] * (p2[0] * p3[1] - p2[1] * p3[0]))
