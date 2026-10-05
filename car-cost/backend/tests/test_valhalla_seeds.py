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


def _fastener_ref(row: dict) -> str:
    """Une ligne `vis_boulon_standard — Radiateur -> structure` est montée
    comme la pièce partagée `FIX-VIS-BOULON-STANDARD`."""
    return "FIX-" + row["nom"].split(" — ", 1)[0].upper().replace("_", "-")


def test_the_hybrid_keeps_every_price_of_the_source_file():
    """Chaque ligne garde son prix ; une fixation le porte via son type."""
    source = _source("aston_martin_valhalla_hybride_phev.json")
    prices = _prices("hybride", "VALH")
    expected = {
        _fastener_ref(row) if ref.startswith("FAST-") else ref: row["prix_unitaire"]["prix_eur"]
        for ref, row in source.items()
    }
    assert set(prices) == set(expected)
    assert all(
        prices[_fastener_ref(row) if ref.startswith("FAST-") else ref]
        == row["prix_unitaire"]["prix_eur"]
        for ref, row in source.items()
    )


@pytest.mark.parametrize("variant, prefix, name", [
    ("hybride", "VALH", "aston_martin_valhalla_hybride_phev.json"),
    ("thermique", "VALT", "aston_martin_valhalla_thermique.json"),
    ("electrique", "VALE", "aston_martin_valhalla_electrique.json"),
])
def test_fasteners_are_shared_and_keep_their_quantities(variant, prefix, name):
    """Comme la vis M6 du Multipla : une pièce par type, sous plusieurs
    ensembles, et autant de vis au total que d'interfaces dans le fichier."""
    expected: dict[str, Decimal] = {}
    for ref, row in _source(name).items():
        if ref.startswith("FAST-"):
            key = f"{prefix}-{_fastener_ref(row)}"
            expected[key] = expected.get(key, Decimal(0)) + Decimal(row["quantite"])
    totals: dict[str, Decimal] = {}
    parents: dict[str, set[str]] = {}
    with (SEEDS / variant / "edges.csv").open(encoding="utf-8") as edges:
        for edge in csv.DictReader(edges):
            if "-FIX-" in edge["child_ref"]:
                child = edge["child_ref"]
                totals[child] = totals.get(child, Decimal(0)) + Decimal(edge["quantity"])
                parents.setdefault(child, set()).add(edge["parent_ref"])
    assert totals == expected
    assert any(len(owners) > 1 for owners in parents.values())


def test_only_the_powertrain_of_a_hypothetical_variant_is_recalibrated():
    """Une pièce commune — la monocoque — coûte le même prix sur les trois
    variantes ; seule la motorisation change d'échelle."""
    source = _source("aston_martin_valhalla_electrique.json")
    prices = _prices("electrique", "VALE")
    factor = Decimal(_report("electrique")["calibration"]["price_factor"])
    assert prices["BOM-0006"] == source["BOM-0006"]["prix_unitaire"]["prix_eur"]
    pack = next(ref for ref, row in source.items() if row["nom"].startswith("Pack batterie HV"))
    assert prices[pack] == (source[pack]["prix_unitaire"]["prix_eur"] * factor).quantize(Decimal("0.01"))
