"""Densités du jeu de données (ADR-0017 §4) : du CSV jusqu'au domaine.

Données synthétiques : aucune de ces valeurs ne vient d'un constructeur.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from carcost.infrastructure.seed_loader import (
    PART_COLUMNS,
    build_load_script,
    read_seeds,
)

SEEDS = Path(__file__).resolve().parents[3] / "seeds"


def test_the_multipla_seeds_declare_densities_of_materials_by_mass():
    with (SEEDS / "parts.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["part_ref"]: row for row in csv.DictReader(handle)}

    assert rows["MAT-STEEL-SHEET"]["density_kg_m3"] == "7850"
    assert rows["MAT-ALU-SHEET"]["density_kg_m3"] == "2700"
    assert rows["MAT-ABS-GRANULE"]["density_kg_m3"] == "1050"
    assert rows["MAT-COPPER-WIRE"]["density_kg_m3"] == "8960"
    assert rows["MAT-PAINT-BASE"]["density_kg_m3"] == ""
    assert rows["MAT-FOAM-PU"]["density_kg_m3"] == ""
    others = [
        ref
        for ref, row in rows.items()
        if not ref.startswith("MAT-") and row["density_kg_m3"] != ""
    ]
    assert others == []


def test_the_load_script_copies_densities():
    script = build_load_script(**read_seeds(SEEDS))

    header = next(line for line in script.splitlines() if line.startswith("COPY part ("))
    assert "density_kg_m3" in header
    column = PART_COLUMNS.index("density_kg_m3")
    alu = next(
        line.split("\t")
        for line in script.splitlines()
        if line.startswith("bom-multipla-2026-09-22\tMAT-ALU-SHEET\t")
    )
    assert alu[column] == "2700"


def test_rows_without_density_load_as_null():
    script = build_load_script(**read_seeds(SEEDS / "valhalla" / "hybride"))

    lines = script.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("COPY part ("))
    end = lines.index("\\.", start)
    column = PART_COLUMNS.index("density_kg_m3")
    part_lines = lines[start + 1 : end]
    assert part_lines
    assert all(line.split("\t")[column] == "\\N" for line in part_lines)


def test_seed_bom_reads_material_and_density():
    from carcost.infrastructure.seed_loader import seed_bom

    bom = seed_bom(SEEDS)

    assert bom.parts["CAR-HOOD-SHELL"].material_ref == "MAT-STEEL-SHEET"
    assert bom.parts["MAT-STEEL-SHEET"].density_kg_m3 == Decimal("7850")
