"""Les trois Valhalla telles qu'importées : ce qui vient de la PR et ce qui est recalé.

Lit les fichiers du dépôt, pas un double : ce sont eux que le chargeur met en
base. Le recalage des prix ne doit toucher que la motorisation des variantes
hypothétiques, et tenir leur coût à ±5 % de l'hybride.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

SEEDS = Path(__file__).resolve().parents[2] / "seeds" / "valhalla"


def _report(variant: str) -> dict:
    return json.loads((SEEDS / variant / "validation_report.json").read_text(encoding="utf-8"))


def _cost(variant: str) -> Decimal:
    return Decimal(_report(variant)["costing"]["total_cost_exact"])


def _source(name: str) -> dict:
    document = json.loads((SEEDS / "source" / name).read_text(encoding="utf-8"), parse_float=Decimal)
    rows = {}
    for content in document["categories"].values():
        groups = content.values() if isinstance(content, dict) else [content]
        for group in groups:
            for row in group:
                rows[row["id"]] = row
    return rows


def _prices(variant: str, prefix: str) -> dict[str, Decimal]:
    with (SEEDS / variant / "parts.csv").open(encoding="utf-8") as source:
        return {
            row["part_ref"].removeprefix(prefix + "-"): Decimal(row["base_price_eur"])
            for row in csv.DictReader(source)
            if row["valuation_mode"] == "purchased"
        }


@pytest.mark.parametrize(
    "variant, ratio", [("thermique", Decimal("0.95")), ("electrique", Decimal("1.05"))]
)
def test_hypothetical_variants_stay_within_five_percent_of_the_hybrid(variant, ratio):
    observed = _cost(variant) / _cost("hybride")
    assert abs(observed - ratio) < Decimal("0.001")


def test_the_hybrid_keeps_every_price_of_the_source_file():
    source = _source("aston_martin_valhalla_hybride_phev.json")
    prices = _prices("hybride", "VALH")
    assert set(prices) == set(source)
    assert all(prices[ref] == source[ref]["prix_unitaire"]["prix_eur"] for ref in source)


def test_only_the_powertrain_of_a_hypothetical_variant_is_recalibrated():
    """Une pièce commune — la monocoque — coûte le même prix sur les trois
    variantes ; seule la motorisation change d'échelle."""
    source = _source("aston_martin_valhalla_electrique.json")
    prices = _prices("electrique", "VALE")
    factor = Decimal(_report("electrique")["calibration"]["price_factor"])
    assert prices["BOM-0006"] == source["BOM-0006"]["prix_unitaire"]["prix_eur"]
    pack = next(ref for ref, row in source.items() if row["nom"].startswith("Pack batterie HV"))
    assert prices[pack] == (source[pack]["prix_unitaire"]["prix_eur"] * factor).quantize(Decimal("0.01"))
