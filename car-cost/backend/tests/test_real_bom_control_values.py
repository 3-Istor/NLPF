"""Le moteur confronté à la nomenclature réelle de la Multipla.

Les 474 quantités cumulées du jeu de données ont été calculées par deux
algorithmes indépendants, puis figées. Si le moteur en contredit une seule, il a
tort — pas le fichier.

Ce test lit un fichier : ce n'est donc pas un test de domaine, et il vit hors du
dossier `domain`. Le moteur, lui, ne sait toujours pas ce qu'est un fichier.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from carcost.domain.bom import Bom, Edge, Part, ValuationMode
from carcost.domain.engine import compute
from carcost.domain.scenario import CalculationInput

SEEDS = Path(__file__).resolve().parents[2] / "seeds" / "bom_multipla.json"


@pytest.fixture(scope="module")
def dataset() -> dict:
    return json.loads(SEEDS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def multipla(dataset: dict) -> Bom:
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


@pytest.fixture(scope="module")
def result(multipla: Bom, dataset: dict):
    """Le scénario vide : prix de base, sans multiplicateur ni coefficient.

    Les leviers de sourcing appartiennent à la couche application ; le moteur
    reçoit des prix unitaires déjà résolus.
    """
    prices = {
        row["part_ref"]: Decimal(row["base_price_eur"]) / Decimal(row["price_per"])
        for row in dataset["parts"]
        if row["base_price_eur"]
    }
    return compute(
        CalculationInput(
            bom=multipla,
            unit_prices=prices,
            labour_rate=Decimal("42.00"),
            active_rules=frozenset({"labour"}),
        )
    )


def test_every_cumulative_quantity_matches_the_dataset(dataset, result) -> None:
    expected = {
        row["part_ref"]: Decimal(row["expected_cumulative_quantity"])
        for row in dataset["parts"]
    }

    computed = {line.part_ref: line.cumulative_quantity for line in result.lines}

    assert computed == expected


@pytest.mark.parametrize(
    ("part_ref", "quantity", "why"),
    [
        ("ENG-PISTON-RING", "12", "3 segments × 4 attelages mobiles"),
        ("CHS-TIRE-185-65-15", "5", "4 roues + la roue de secours"),
        ("CAR-GLASS-DOOR-FRONT", "2", "la porte avant est montée deux fois"),
        ("INT-SEAT-ASSY", "6", "3 places avant + 3 arrière"),
        ("CAR-DOOR-HINGE", "12", "4 portes + capot + hayon, 2 charnières chacun"),
        ("ENG-MOUNT-ASSY", "4", "3 supports moteur + 1 support de boîte"),
    ],
)
def test_hand_checkable_quantities(result, part_ref, quantity, why) -> None:
    assert result.line(part_ref).cumulative_quantity == Decimal(quantity), why


def test_no_price_is_missing(result) -> None:
    assert result.parts_without_price == ()
    assert not result.parts_without_price


def test_contributions_sum_to_the_total(result) -> None:
    total = sum((line.own_contribution for line in result.lines), Decimal(0))

    assert total == result.total_cost


def test_root_full_cost_equals_the_total(result, multipla) -> None:
    """Le véhicule coûte ce que coûtent ses pièces : dit deux fois, sans écart."""
    assert result.line(multipla.root_ref).full_unit_cost == result.total_cost


def test_a_shared_part_is_not_undercounted(result) -> None:
    """La tôle est employée par 29 parents ; un arbre en verrait une fraction."""
    assert result.line("MAT-STEEL-SHEET").cumulative_quantity == Decimal("297.300000")
    assert result.line("MAT-STEEL-SHEET").occurrence_count == 33
