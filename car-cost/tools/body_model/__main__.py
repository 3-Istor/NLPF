"""Génère la maquette 3D du Multipla : `seeds/body_multipla.glb`, et ses quatre
dérivés de démonstration dans `seeds/demo/` (aileron, capot en aluminium,
capot en surface ouverte, carrosserie en aluminium).

    python -m tools.body_model [--seeds-dir seeds] [--check]

Une voiture-jouet : chaque pièce de carrosserie à matière déclarée sous
CAR-ASSY est un polygone extrudé (placement.py), avec autant de nœuds que
d'emplacements de montage et un seul maillage par pièce. La masse mesurée de
chaque maillage, arrondi₁₀⁻⁶(volume × densité), vaut exactement la quantité
de l'arête pièce → matière (ADR-0017 §3, R1). Plus du décor sans
`extras.carcost`. Maquette synthétique : aucune cote constructeur.

Les dérivés sont la même maquette, octet pour octet sauf ce qui change : même
géométrie, autre matière, un pavé en plus, ou une face en moins. Données
synthétiques. `--check` régénère en mémoire et échoue si un fichier présent diffère.
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

from .placement import COLOURS, DECOR, MIRRORED, PIECES, flank, rectangle

FILE_NAME = "body_multipla.glb"
ROOT = "CAR-ASSY"
ALU = "MAT-ALU-SHEET"
HOOD = "CAR-HOOD-SHELL"
SHELLS = (HOOD, "CAR-PANEL-ROOF", "CAR-DOOR-SHELL-FRONT", "CAR-DOOR-SHELL-REAR", "CAR-TAILGATE-SHELL")
SPOILER = {"ref": "BODY-SPOILER", "parts": {"FIX-M8-20": "4"}}
# Dérivés : nom du fichier -> options de `build`.
DEMOS = {
    "aileron.glb": {"spoiler": True},
    "capot-alu.glb": {"alu": (HOOD,)},
    "capot-surface.glb": {"open_hood": True},
    "carrosserie-alu.glb": {"alu": SHELLS},
}


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


def close(points, caps, contour, size: int):
    """Solide fermé à couches de `size` sommets : `caps` (triangles du sens
    trigonométrique, comme `contour`) ferment la première et la dernière
    couche, des parois relient les couches successives le long du contour.
    Les faces partagent exactement leurs arêtes. Orienté vers l'extérieur."""
    top = len(points) - size
    triangles = [(i, k, j) for i, j, k in caps] + [(top + i, top + j, top + k) for i, j, k in caps]
    for base in range(0, top, size):
        for p, q in zip(contour, contour[1:] + contour[:1]):
            triangles += [(base + p, base + q, base + size + q), (base + p, base + size + q, base + size + p)]
    if volume(points, triangles) < 0:
        triangles = [(i, k, j) for i, j, k in triangles]
    return points, triangles


def prism(polygon, width: float, axis: str, bulge=(0, 0)):
    """Polygone extrudé sur `width`, centré, en sommets float32.

    Avec `bulge`, l'extrusion est découpée en tranches, chacune décalée dans
    le plan du polygone de bulge × (1 − u⁴), u allant de -1 à 1 sur la
    largeur : panneau bombé au milieu, bords adoucis. Chaque tranche garde
    l'aire du polygone, donc volume = aire × largeur comme sans galbe
    (Cavalieri) ; les parois entre tranches sont des parallélogrammes.
    """
    if sum(a0 * b1 - a1 * b0 for (a0, b0), (a1, b1) in zip(polygon, polygon[1:] + polygon[:1])) < 0:
        polygon = polygon[::-1]
    place = {"x": lambda a, b, e: (e, b, a), "y": lambda a, b, e: (a, e, b),
             "z": lambda a, b, e: (a, b, e)}[axis]
    slices = 12 if any(bulge) else 1
    points = []
    for step in range(slices + 1):
        u = 2 * step / slices - 1
        lift = 1 - u * u * u * u
        points += [[f32(c) for c in place(a + bulge[0] * lift, b + bulge[1] * lift, u * width / 2)]
                   for a, b in polygon]
    return close(points, triangulate(polygon), list(range(len(polygon))), len(polygon))


def sheet(columns, t: float, rows: int = 8):
    """Tôle de flanc : grille (z, y) de colonnes `(z, bas, haut)` aux z croissants,
    d'épaisseur t selon X, déportée vers +X de `flank(y)`.

    Les deux faces sont la même surface décalée de t selon X : volume = aire
    du profil × t, exactement comme une tôle plane (Cavalieri).
    """
    grid = [(z, low + (high - low) * j / rows) for z, low, high in columns for j in range(rows + 1)]
    points = [[f32(flank(y) + e), f32(y), f32(z)] for e in (-t / 2, t / 2) for z, y in grid]
    at = lambda i, j: i * (rows + 1) + j  # noqa: E731
    m = len(columns)
    caps = [tri for i in range(m - 1) for j in range(rows)
            for tri in ((at(i, j), at(i + 1, j), at(i + 1, j + 1)), (at(i, j), at(i + 1, j + 1), at(i, j + 1)))]
    contour = ([at(i, 0) for i in range(m)] + [at(m - 1, j) for j in range(1, rows + 1)]
               + [at(i, rows) for i in range(m - 2, -1, -1)] + [at(0, j) for j in range(rows - 1, 0, -1)])
    return close(points, caps, contour, len(grid))


def mesh(shape):
    """Maillage d'une forme de placement.py : tôle de flanc ou polygone extrudé."""
    return sheet(*shape[1:]) if shape[0] == "sheet" else prism(*shape)


def mirror(points, triangles):
    """Reflet X → -X, exact en float32 ; l'ordre inversé garde le volume, positif et égal."""
    return [[-x, y, z] for x, y, z in points], [(i, k, j) for i, j, k in triangles]


SMOOTH = 0.8660254037844387  # cos 30° : en deçà, deux facettes voisines sont lissées ensemble


def smooth_normals(points, triangles):
    """Sommets dédoublés par normale : chaque coin prend la moyenne (pondérée par
    l'aire) des facettes qui touchent sa position à moins de 30° de la sienne.
    Galbes lisses, arêtes vives ; les positions, donc les volumes, ne bougent pas."""
    faces = []
    for a, b, c in triangles:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points[a], points[b], points[c]
        n = ((by - ay) * (cz - az) - (bz - az) * (cy - ay), (bz - az) * (cx - ax) - (bx - ax) * (cz - az),
             (bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
        length = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
        if length == 0:
            sys.exit("triangle dégénéré : normale indéfinie")
        faces.append((n, [c / length for c in n]))
    touching = {}
    for f, tri in enumerate(triangles):
        for i in tri:
            touching.setdefault(tuple(points[i]), []).append(f)
    vertices, indices = {}, []
    for f, tri in enumerate(triangles):
        unit = faces[f][1]
        for i in tri:
            position = tuple(points[i])
            total = [sum(faces[g][0][k] for g in touching[position]
                         if sum(u * v for u, v in zip(faces[g][1], unit)) > SMOOTH) for k in range(3)]
            length = math.sqrt(sum(c * c for c in total))
            normal = tuple(f32(c / length) for c in total)
            indices.append(vertices.setdefault((position, normal), len(vertices)))
    return list(vertices), [tuple(indices[k:k + 3]) for k in range(0, len(indices), 3)]


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
        points, triangles = mesh(shape(t))
        t *= float(target / volume(points, triangles))
    points, triangles = mesh(shape(t))
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


def build(seeds_dir: Path, alu=(), spoiler=False, open_hood=False) -> bytes:
    """La maquette ; `alu` : pièces passées en aluminium, `spoiler` : un aileron
    sur le pavillon, `open_hood` : le capot privé d'une face (surface ouverte)."""
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
            "copyright": "Données synthétiques : aucune cote ni masse constructeur"
            if (alu or spoiler or open_hood) else "Maquette synthétique : aucune cote ni masse constructeur",
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
        vertices, triangles = smooth_normals(points, triangles)
        positions = [list(position) for position, _ in vertices]
        accessors = document["accessors"]
        accessors.append({
            "bufferView": add_view(struct.pack(f"<{3 * len(positions)}f", *sum(positions, []))),
            "componentType": 5126, "count": len(positions), "type": "VEC3",
            "min": [min(c) for c in zip(*positions)], "max": [max(c) for c in zip(*positions)],
        })
        accessors.append({
            "bufferView": add_view(struct.pack(f"<{3 * len(vertices)}f",
                                               *(c for _, normal in vertices for c in normal))),
            "componentType": 5126, "count": len(vertices), "type": "VEC3",
        })
        accessors.append({
            "bufferView": add_view(struct.pack(f"<{3 * len(triangles)}H", *sum(triangles, ()))),
            "componentType": 5123, "count": 3 * len(triangles), "type": "SCALAR",
        })
        document["meshes"].append({"primitives": [{
            "attributes": {"POSITION": len(accessors) - 3, "NORMAL": len(accessors) - 2},
            "indices": len(accessors) - 1,
            "material": names.index(material),
        }]})
        return len(document["meshes"]) - 1

    def add_nodes(name: str, centers, mesh_at, extras=None) -> None:
        for number, center in enumerate(centers, 1):
            node = {"name": f"{name} {number}", "mesh": mesh_at(center), "translation": list(center)}
            if extras:
                node["extras"] = extras
            document["scenes"][0]["nodes"].append(len(document["nodes"]))
            document["nodes"].append(node)

    for ref, (count, quantity, density) in pieces.items():
        shape, centers = PIECES[ref]
        if len(centers) != count:
            sys.exit(f"{ref} : {len(centers)} emplacements, la nomenclature en monte {count}")
        points, triangles = fit(ref, shape, quantity, density)
        if open_hood and ref == HOOD:
            triangles = triangles[1:]
        material = ALU if ref in alu else bom.parts[ref].material_ref
        left = add_mesh(points, triangles, material)
        # Flancs et portes : l'emplacement de droite reçoit le miroir, de même masse.
        right = add_mesh(*mirror(points, triangles), material) if ref in MIRRORED else left
        add_nodes(ref, centers, lambda c: right if c[0] < 0 else left, {"carcost": {"ref": ref}})
    for name, (shape, material, centers) in DECOR.items():
        index = add_mesh(*prism(*shape), material)
        add_nodes(name, centers, lambda c: index)
    if spoiler:  # 1,20 × 0,25 × 0,010 m, posé en haut à l'arrière du pavillon
        index = add_mesh(*prism(rectangle(1.2, 0.25), 0.01, "y"), "MAT-ABS-GRANULE")
        document["scenes"][0]["nodes"].append(len(document["nodes"]))
        document["nodes"].append({"name": "Aileron", "mesh": index, "translation": [0, 1.72, -1.78],
                                  "extras": {"carcost": SPOILER}})

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

    files = {args.seeds_dir / FILE_NAME: build(args.seeds_dir)}
    for name, options in DEMOS.items():
        files[args.seeds_dir / "demo" / name] = build(args.seeds_dir, **options)
    if args.check:
        differences = [
            f"{path.name} : {'absent du dépôt' if not path.exists() else 'diffère de la régénération'}"
            for path, data in files.items() if not path.exists() or path.read_bytes() != data
        ]
        if not differences:
            print("Déterminisme vérifié : la maquette et ses dérivés régénérés sont identiques.")
            return 0
        print("DÉTERMINISME — ÉCHEC", file=sys.stderr)
        for difference in differences:
            print(f"  - {difference}", file=sys.stderr)
        return 1

    (args.seeds_dir / "demo").mkdir(exist_ok=True)
    for path, data in files.items():
        path.write_bytes(data)
        print(f"{path} écrit : {len(data)} octets (données synthétiques)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
