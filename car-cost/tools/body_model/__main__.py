"""Génère la maquette 3D du Multipla : `seeds/body_multipla.glb`.

    python -m tools.body_model [--seeds-dir seeds] [--check]

Une voiture-jouet : chaque pièce de carrosserie à matière déclarée sous
CAR-ASSY est un polygone extrudé (placement.py), avec autant de nœuds que
d'emplacements de montage et un seul maillage par pièce. La masse mesurée de
chaque maillage, arrondi₁₀⁻⁶(volume × densité), vaut exactement la quantité
de l'arête pièce → matière (ADR-0017 §3, R1). Plus du décor sans
`extras.carcost`. Maquette synthétique : aucune cote constructeur.

`--check` régénère en mémoire et échoue si le fichier présent diffère.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from carcost.infrastructure.seed_loader import seed_bom

from .placement import COLOURS, DECOR, PIECES

FILE_NAME = "body_multipla.glb"
ROOT = "CAR-ASSY"


def f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def f32_step(x: float, k: int) -> float:
    """Le k-ième float32 voisin de x (x > 0)."""
    bits = struct.unpack("<I", struct.pack("<f", x))[0]
    return struct.unpack("<f", struct.pack("<I", bits + k))[0]


def micro(mass: Fraction) -> int:
    """arrondi₁₀⁻⁶ en ROUND_HALF_UP, en millionièmes de kg."""
    return math.floor(mass * 10**6 + Fraction(1, 2))


def body_pieces(bom) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    """{ref: (quantité cumulée sous CAR-ASSY, quantité de matière, densité)}."""
    cumulative = Counter()

    def walk(ref, quantity):
        cumulative[ref] += quantity
        for child, per_unit in bom.children_of(ref):
            walk(child, quantity * per_unit)

    walk(ROOT, Decimal(1))
    pieces = {}
    for ref in sorted(cumulative):
        part = bom.parts[ref]
        if part.material_ref and not part.is_purchased:
            material = dict(bom.children_of(ref))[part.material_ref]
            pieces[ref] = (cumulative[ref], material, bom.parts[part.material_ref].density_kg_m3)
    return pieces


def triangulate(polygon) -> list[tuple[int, int, int]]:
    """Découpe en oreilles d'un polygone simple parcouru dans le sens trigonométrique."""

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    left, triangles = list(range(len(polygon))), []
    while len(left) > 3:
        for m in range(len(left)):
            i, j, k = left[m - 1], left[m], left[(m + 1) % len(left)]
            a, b, c = polygon[i], polygon[j], polygon[k]
            if cross(a, b, c) > 0 and not any(
                cross(a, b, p) > 0 and cross(b, c, p) > 0 and cross(c, a, p) > 0
                for p in (polygon[n] for n in left if n not in (i, j, k))
            ):
                triangles.append((i, j, k))
                left.pop(m)
                break
        else:
            sys.exit("polygone non simple : aucune oreille")
    return triangles + [tuple(left)]


def volume(points, triangles) -> Fraction:
    """Volume signé exact (produit mixte) des sommets float32."""
    total = Fraction(0)
    for a, b, c in triangles:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = (map(Fraction, points[i]) for i in (a, b, c))
        total += ax * (by * cz - bz * cy) + ay * (bz * cx - bx * cz) + az * (bx * cy - by * cx)
    return total / 6


def prism(polygon, width: float, axis: str, bulge=(0, 0)):
    """Polygone extrudé sur `width`, centré : sommets float32, faces vers l'extérieur.

    Avec `bulge`, l'extrusion est découpée en tranches, chacune décalée dans
    le plan du polygone de bulge × (1 − u⁴), u allant de -1 à 1 sur la
    largeur : panneau bombé au milieu, bords adoucis. Chaque tranche garde
    l'aire du polygone, donc volume = aire × largeur comme sans galbe
    (Cavalieri) ; les parois entre tranches sont des parallélogrammes.
    Les faces partagent exactement leurs arêtes : le maillage est fermé.
    """
    if sum(a0 * b1 - a1 * b0 for (a0, b0), (a1, b1) in zip(polygon, polygon[1:] + polygon[:1])) < 0:
        polygon = polygon[::-1]
    place = {"x": lambda a, b, e: (e, b, a), "y": lambda a, b, e: (a, e, b),
             "z": lambda a, b, e: (a, b, e)}[axis]
    n, slices = len(polygon), 12 if any(bulge) else 1
    points = []
    for step in range(slices + 1):
        u = 2 * step / slices - 1
        lift = 1 - u * u * u * u
        points += [[f32(c) for c in place(a + bulge[0] * lift, b + bulge[1] * lift, u * width / 2)]
                   for a, b in polygon]
    caps = triangulate(polygon)
    top = n * slices
    triangles = [(i, k, j) for i, j, k in caps] + [(top + i, top + j, top + k) for i, j, k in caps]
    for base in range(0, top, n):
        for i in range(n):
            j = (i + 1) % n
            triangles += [(base + i, base + j, base + n + j), (base + i, base + n + j, base + n + i)]
    if volume(points, triangles) < 0:
        triangles = [(i, k, j) for i, j, k in triangles]
    return points, triangles


def fit(ref: str, shape, quantity: Decimal, density: Decimal):
    """Maillage float32 de `shape(t)` dont le volume × densité s'arrondit à `quantity`.

    t approché par point fixe, puis on retouche une coordonnée à la fois :
    le volume est linéaire en chaque coordonnée, de pente le gradient exact.
    On prend la plus forte pente dont un pas float32 ne dépasse pas l'écart
    restant, qui diminue au moins de moitié à chaque tour.
    """
    if density is None:
        sys.exit(f"{ref} : la matière n'a pas de densité, la pièce n'est pas mesurable")
    target = Fraction(quantity) / Fraction(density)
    t = 0.001
    for _ in range(6):
        points, triangles = prism(*shape(t))
        t *= float(target / volume(points, triangles))
    points, triangles = prism(*shape(t))
    for _ in range(60):
        measured = volume(points, triangles)
        if micro(measured * Fraction(density)) == micro(Fraction(quantity)):
            return points, triangles
        error = target - measured
        gradient = [[Fraction(0)] * 3 for _ in points]
        for a, b, c in triangles:
            for i, p, q in ((a, points[b], points[c]), (b, points[c], points[a]),
                            (c, points[a], points[b])):
                p, q = list(map(Fraction, p)), list(map(Fraction, q))
                gradient[i][0] += p[1] * q[2] - p[2] * q[1]
                gradient[i][1] += p[2] * q[0] - p[0] * q[2]
                gradient[i][2] += p[0] * q[1] - p[1] * q[0]
        slope, i, k = max(
            (abs(g) / 6, i, k) for i, row in enumerate(gradient) for k, g in enumerate(row)
            if 0 < abs(g) / 6 * (Fraction(f32_step(abs(points[i][k]), 1)) - Fraction(abs(points[i][k])))
            <= abs(error)
        )
        points[i][k] = f32(float(Fraction(points[i][k]) + error / (gradient[i][k] / 6)))
    sys.exit(f"{ref} : aucun maillage float32 ne pèse exactement {quantity} kg")


def build(seeds_dir: Path) -> bytes:
    bom = seed_bom(seeds_dir)
    pieces = body_pieces(bom)
    if set(pieces) != set(PIECES):
        sys.exit(
            "table de placement et nomenclature divergent : "
            f"manquent {sorted(set(pieces) - set(PIECES))}, "
            f"en trop {sorted(set(PIECES) - set(pieces))}"
        )

    binary = bytearray()
    document = {
        "asset": {
            "version": "2.0",
            "generator": "tools.body_model",
            "copyright": "Maquette synthétique : aucune cote ni masse constructeur",
        },
        "scene": 0,
        "scenes": [{"nodes": []}],
        "nodes": [],
        "meshes": [],
        "materials": [],
        "accessors": [],
        "bufferViews": [],
        "buffers": [],
    }

    def add_view(data: bytes) -> int:
        binary.extend(b"\0" * (-len(binary) % 4))
        document["bufferViews"].append(
            {"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)}
        )
        binary.extend(data)
        return len(document["bufferViews"]) - 1

    def add_mesh(points, triangles, material: str) -> int:
        names = [m["name"] for m in document["materials"]]
        if material not in names:
            colour = COLOURS[material]
            entry = {"name": material, "pbrMetallicRoughness": {
                "baseColorFactor": colour, "metallicFactor": 0.0, "roughnessFactor": 0.6}}
            if colour[3] < 1:
                entry["alphaMode"] = "BLEND"
            document["materials"].append(entry)
            names.append(material)
        accessors = document["accessors"]
        accessors.append({
            "bufferView": add_view(struct.pack(f"<{3 * len(points)}f", *sum(points, []))),
            "componentType": 5126, "count": len(points), "type": "VEC3",
            "min": [min(c) for c in zip(*points)], "max": [max(c) for c in zip(*points)],
        })
        accessors.append({
            "bufferView": add_view(struct.pack(f"<{3 * len(triangles)}H", *sum(triangles, ()))),
            "componentType": 5123, "count": 3 * len(triangles), "type": "SCALAR",
        })
        document["meshes"].append({"primitives": [{
            "attributes": {"POSITION": len(accessors) - 2},
            "indices": len(accessors) - 1,
            "material": names.index(material),
        }]})
        return len(document["meshes"]) - 1

    def add_nodes(name: str, mesh: int, centers, extras=None) -> None:
        for number, center in enumerate(centers, 1):
            node = {"name": f"{name} {number}", "mesh": mesh, "translation": list(center)}
            if extras:
                node["extras"] = extras
            document["scenes"][0]["nodes"].append(len(document["nodes"]))
            document["nodes"].append(node)

    for ref, (count, quantity, density) in pieces.items():
        shape, centers = PIECES[ref]
        if len(centers) != count:
            sys.exit(f"{ref} : {len(centers)} emplacements, la nomenclature en monte {count}")
        mesh = add_mesh(*fit(ref, shape, quantity, density), bom.parts[ref].material_ref)
        add_nodes(ref, mesh, centers, {"carcost": {"ref": ref}})
    for name, (shape, material, centers) in DECOR.items():
        add_nodes(name, add_mesh(*prism(*shape), material), centers)

    document["buffers"].append({"byteLength": len(binary)})
    text = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(binary)
    return b"".join([
        struct.pack("<4sII", b"glTF", 2, total),
        struct.pack("<II", len(text), 0x4E4F534A), text,
        struct.pack("<II", len(binary), 0x004E4942), bytes(binary),
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds-dir", default="seeds", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="ne rien écrire et échouer si le fichier présent diffère",
    )
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    data = build(args.seeds_dir)
    path = args.seeds_dir / FILE_NAME
    if args.check:
        if not path.exists():
            difference = f"{FILE_NAME} : absent du dépôt"
        elif path.read_bytes() != data:
            difference = f"{FILE_NAME} : diffère de la régénération"
        else:
            print("Déterminisme vérifié : la maquette régénérée est identique.")
            return 0
        print("DÉTERMINISME — ÉCHEC", file=sys.stderr)
        print(f"  - {difference}", file=sys.stderr)
        return 1

    path.write_bytes(data)
    print(f"{path} écrit : {len(data)} octets (maquette synthétique)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
