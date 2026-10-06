"""Génère la maquette 3D du Multipla : `seeds/body_multipla.glb`.

    python -m tools.body_model [--seeds-dir seeds] [--check]

Un pavé par pièce de carrosserie à matière déclarée sous CAR-ASSY, autant de
nœuds que d'emplacements de montage, un seul maillage par pièce. La masse
mesurée de chaque pavé, arrondi₁₀⁻⁶(volume × densité), vaut exactement la
quantité de l'arête pièce → matière (ADR-0017 §3, R1). Plus du décor sans
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

from .placement import DECOR, PIECES

FILE_NAME = "body_multipla.glb"
ROOT = "CAR-ASSY"
# Sommets d'un pavé : bit 0 → +X, bit 1 → +Y, bit 2 → +Z. Faces vues de
# l'extérieur dans le sens trigonométrique : le volume signé est positif.
TRIANGLES = (0, 4, 6, 0, 6, 2, 1, 3, 7, 1, 7, 5, 0, 1, 5, 0, 5, 4,
             2, 6, 7, 2, 7, 3, 0, 2, 3, 0, 3, 1, 4, 5, 7, 4, 7, 6)


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


def solve(ref: str, sides, quantity: Decimal, density: Decimal) -> list[float]:
    """Côtés float32 dont le volume × densité s'arrondit à `quantity`.

    L'épaisseur (côté `None`) est calculée, puis on essaie les float32 voisins
    du premier côté donné jusqu'à tomber juste.
    """
    if density is None:
        sys.exit(f"{ref} : la matière n'a pas de densité, la pièce n'est pas mesurable")
    free = sides.index(None)
    a, b = (f32(s) for s in sides if s is not None)
    target = micro(Fraction(quantity))
    for k in range(4000):
        candidate = f32_step(a, k // 2 if k % 2 else -(k // 2))
        base = Fraction(candidate) * Fraction(b)
        start = f32(float(Fraction(quantity) / Fraction(density) / base))
        for j in (-1, 0, 1):
            thickness = f32_step(start, j)
            if micro(base * Fraction(thickness) * Fraction(density)) == target:
                found = [candidate, b]
                found.insert(free, thickness)
                return found
    sys.exit(f"{ref} : aucun pavé float32 ne pèse exactement {quantity} kg")


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
        document["bufferViews"].append(
            {"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)}
        )
        binary.extend(data)
        return len(document["bufferViews"]) - 1

    def add_box(sides, material: str) -> int:
        half = [s / 2 for s in sides]
        corners = [[half[axis] if i >> axis & 1 else -half[axis] for axis in range(3)]
                   for i in range(8)]
        names = [m["name"] for m in document["materials"]]
        if material not in names:
            document["materials"].append({"name": material})
            names.append(material)
        accessors = document["accessors"]
        accessors.append({
            "bufferView": add_view(struct.pack("<24f", *sum(corners, []))),
            "componentType": 5126, "count": 8, "type": "VEC3",
            "min": [-h for h in half], "max": half,
        })
        accessors.append({
            "bufferView": add_view(struct.pack("<36H", *TRIANGLES)),
            "componentType": 5123, "count": 36, "type": "SCALAR",
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
        sides, centers = PIECES[ref]
        if len(centers) != count:
            sys.exit(f"{ref} : {len(centers)} emplacements, la nomenclature en monte {count}")
        mesh = add_box(solve(ref, sides, quantity, density), bom.parts[ref].material_ref)
        add_nodes(ref, mesh, centers, {"carcost": {"ref": ref}})
    for name, (sides, centers) in DECOR.items():
        add_nodes(name, add_box([f32(s) for s in sides], "DECOR"), centers)

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
