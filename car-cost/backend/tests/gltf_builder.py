"""Petit constructeur de GLB pour les tests du lecteur (indépendant de la maquette)."""

from __future__ import annotations

import json
import struct


def f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def glb(document: dict | bytes, binary: bytes = b"", version: int = 2) -> bytes:
    text = document if isinstance(document, bytes) else json.dumps(document).encode()
    text += b" " * (-len(text) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = (
        struct.pack("<II", len(text), 0x4E4F534A) + text
        + struct.pack("<II", len(binary), 0x004E4942) + binary
    )
    return struct.pack("<4sII", b"glTF", version, 12 + len(chunks)) + chunks


def box(sx: float, sy: float, sz: float):
    """Pavé centré : 8 coins (bit 0 → x, bit 1 → y, bit 2 → z), 12 triangles
    tournés vers l'extérieur ; les deux derniers forment la face du dessus."""
    half = [f32(s) / 2 for s in (sx, sy, sz)]
    corners = [
        tuple(half[axis] if i >> axis & 1 else -half[axis] for axis in range(3))
        for i in range(8)
    ]
    quads = [(0, 2, 3, 1), (1, 3, 7, 5), (0, 4, 6, 2), (2, 6, 7, 3), (0, 1, 5, 4), (4, 5, 7, 6)]
    triangles = [t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))]
    return corners, triangles


def model(positions, triangles, nodes=None, *, indexed=True, stride=12,
          material=None, extensions_required=None) -> bytes:
    """Un GLB à un maillage (une primitive), instancié par `nodes`."""
    if indexed:
        vertices, indices = positions, [i for t in triangles for i in t]
    else:
        vertices, indices = [positions[i] for t in triangles for i in t], []
    pos = b"".join(struct.pack("<3f", *p) + b"\0" * (stride - 12) for p in vertices)
    idx = struct.pack(f"<{len(indices)}H", *indices)
    pos_view = {"buffer": 0, "byteOffset": 0, "byteLength": len(pos)}
    if stride != 12:
        pos_view["byteStride"] = stride
    views = [pos_view]
    accessors = [{"bufferView": 0, "componentType": 5126, "count": len(vertices), "type": "VEC3"}]
    primitive = {"attributes": {"POSITION": 0}}
    if indexed:
        views.append({"buffer": 0, "byteOffset": len(pos), "byteLength": len(idx)})
        accessors.append({"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"})
        primitive["indices"] = 1
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(pos) + len(idx)}],
        "bufferViews": views,
        "accessors": accessors,
        "meshes": [{"primitives": [primitive]}],
        "nodes": nodes if nodes is not None else [{"mesh": 0}],
    }
    if material is not None:
        document["materials"] = [{"name": material}]
        primitive["material"] = 0
    if extensions_required:
        document["extensionsRequired"] = extensions_required
    return glb(document, pos + idx)
