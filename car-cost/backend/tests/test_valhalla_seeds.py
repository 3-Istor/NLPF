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


def _parts(variant: str) -> dict[str, dict]:
    with (SEEDS / variant / "parts.csv").open(encoding="utf-8") as source:
        return {row["part_ref"]: row for row in csv.DictReader(source)}


#: Le taux de l'atelier Valhalla : 60 EUR/h, une minute coûte un euro.
LABOUR_EUR_PER_MINUTE = Decimal(1)


def _unit_costs(variant: str, prefix: str) -> dict[str, Decimal]:
    """Coût d'une unité de chaque pièce, enfants et main-d'œuvre compris.

    Une pièce achetée vaut son prix ; une pièce décomposée en ensemble (detail.py)
    vaut ce que coûtent ses composants plus sa main-d'œuvre. Recalculé ici à la
    main, sans le moteur : c'est le fichier livré qui est vérifié.
    """
    parts = _parts(variant)
    children: dict[str, list[tuple[str, Decimal]]] = {}
    for edge in _edges(variant):
        children.setdefault(edge["parent_ref"], []).append(
            (edge["child_ref"], Decimal(edge["quantity"]))
        )
    costs: dict[str, Decimal] = {}

    def cost(ref: str) -> Decimal:
        if ref not in costs:
            row = parts[ref]
            if row["valuation_mode"] == "purchased":
                costs[ref] = Decimal(row["base_price_eur"])
            else:
                costs[ref] = Decimal(row["labour_minutes"]) * LABOUR_EUR_PER_MINUTE + sum(
                    (q * cost(child) for child, q in children.get(ref, [])), Decimal(0)
                )
        return costs[ref]

    return {ref.removeprefix(prefix + "-"): cost(ref) for ref in parts}


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


def _edges(variant: str) -> list[dict]:
    with (SEEDS / variant / "edges.csv").open(encoding="utf-8") as edges:
        return list(csv.DictReader(edges))


def test_the_hybrid_keeps_every_price_of_the_source_file():
    """Une ligne du fichier garde son prix, qu'elle reste achetée ou qu'elle
    soit décomposée : ses composants et sa main-d'œuvre le redonnent au
    millionième. Une ligne regroupée avec ses symétriques porte la référence
    de la première ; les autres n'existent plus."""
    source = _source("aston_martin_valhalla_hybride_phev.json")
    costs = _unit_costs("hybride", "VALH")
    kept = [ref for ref in source if ref in costs]
    assert len(kept) > 300
    assert all(costs[ref] == source[ref]["prix_unitaire"]["prix_eur"] for ref in kept)


def test_the_hybrid_is_detailed_like_the_multipla():
    """Composants, matières et zones : environ mille pièces sur cinq niveaux
    et plus, et des matières consommées par des dizaines d'ensembles."""
    parts = _parts("hybride")
    edges = _edges("hybride")
    parents: dict[str, set[str]] = {}
    for edge in edges:
        parents.setdefault(edge["child_ref"], set()).add(edge["parent_ref"])
    assert len(parts) > 900
    assert len(parents["VALH-MAT-PREPREG"]) > 10
    assert sum(1 for owners in parents.values() if len(owners) > 1) > 30
    assert parts["VALH-BOM-0006"]["valuation_mode"] == "manufactured"  # la monocoque


def test_parts_that_differ_only_by_position_are_one_part():
    """Les quatre ressorts sont une pièce × 4 ; les joints homocinétiques,
    avant sous la chaîne électrique et arrière sous la transmission, une
    pièce à deux parents. Un bras inférieur reste distinct d'un supérieur."""
    parts = _parts("hybride")
    refs = {row["label"]: ref for ref, row in parts.items()}
    edges = _edges("hybride")
    under = lambda ref: {(e["parent_ref"], Decimal(e["quantity"])) for e in edges if e["child_ref"] == ref}
    # Un ressort par coin de suspension, quatre coins.
    assert under(refs["Ressort"]) == {("VALH-ZONE-COIN-SUSPENSION", Decimal(1))}
    assert Decimal(parts[refs["Ressort"]]["expected_cumulative_quantity"]) == 4
    assert len(under(refs["Joints homocinétiques"])) == 2
    assert refs["Bras inférieur"] != refs["Bras supérieur"]


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
    prices = _unit_costs("electrique", "VALE")
    factor = Decimal(_report("electrique")["calibration"]["price_factor"])
    assert prices["BOM-0006"] == source["BOM-0006"]["prix_unitaire"]["prix_eur"]
    pack = next(ref for ref, row in source.items() if row["nom"].startswith("Pack batterie HV"))
    assert prices[pack] == (source[pack]["prix_unitaire"]["prix_eur"] * factor).quantize(Decimal("0.01"))
