"""La recherche contre la nomenclature réelle de la Multipla."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from carcost.application.browse_bom import search_parts
from carcost.domain.bom import Bom, Edge, Part, ValuationMode

SEEDS = Path(__file__).resolve().parents[2] / "seeds" / "bom_multipla.json"


@pytest.fixture(scope="module")
def multipla() -> Bom:
    dataset = json.loads(SEEDS.read_text(encoding="utf-8"))
    parts = {
        row["part_ref"]: Part(
            ref=row["part_ref"],
            label=row["label"],
            system=row["system"],
            unit=row["unit"],
            valuation_mode=ValuationMode(row["valuation_mode"]),
            carbon_factor=Decimal(row["carbon_factor_kg_co2e_per_unit"]),
            labour_minutes=(
                Decimal(row["labour_minutes"]) if row["labour_minutes"] else None
            ),
            mass_kg=Decimal(row["mass_kg"]) if row["mass_kg"] else None,
        )
        for row in dataset["parts"]
    }
    edges = tuple(
        Edge(row["parent_ref"], row["child_ref"], Decimal(row["quantity"]))
        for row in dataset["edges"]
    )
    return Bom(
        root_ref=dataset["metadata"]["root_part_ref"], parts=parts, edges=edges
    )


def test_a_part_mounted_33_times_returns_its_33_paths(multipla):
    hits = {hit.part_ref: hit for hit in search_parts(multipla, "tole")}

    hit = hits["MAT-STEEL-SHEET"]
    assert hit.label == "Tôle acier DC04"
    assert len(hit.paths) == 33
    assert hit.paths_truncated is False


def test_electricite_without_accents_finds_the_system_part(multipla):
    labels = [hit.label for hit in search_parts(multipla, "electricite")]

    assert "Électricité et électronique" in labels
