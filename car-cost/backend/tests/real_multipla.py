"""Le vrai Multipla, chiffré en mémoire : nomenclature, offres, prix de référence.

Prix et offres sont ceux du jeu de données, synthétiques (ils ne viennent
d'aucun constructeur ni fournisseur). Le snapshot est fixe : chaque pièce
achetée vaut `base_price_eur / price_per`, ce qui rend les totaux vérifiables
à la main.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from carcost.application.ports import BomVersionSummary
from carcost.application.scenario import Plant, Sourcing, SupplierOffer
from carcost.domain.prices import PriceSnapshot
from carcost.infrastructure.seed_loader import read_seeds, seed_bom

SEEDS = Path(__file__).resolve().parents[2] / "seeds"
MULTIPLA = "bom-multipla-2026-09-22"
TAKEN_AT = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)


def multipla_bom():
    return seed_bom(SEEDS)


def multipla_summary() -> BomVersionSummary:
    seeds = read_seeds(SEEDS)
    meta = seeds["metadata"]
    return BomVersionSummary(
        id=meta["bom_version_id"], label=meta["vehicle"], root_part_ref=meta["root_part_ref"],
        part_count=len(seeds["parts"]), edge_count=len(seeds["edges"]), validated_at=TAKEN_AT,
        is_synthetic=True, reference_labour_rate=Decimal(meta["labour_rate_eur_per_hour"]),
    )


def multipla_sourcing() -> Sourcing:
    suppliers = read_seeds(SEEDS)["suppliers"]
    offers: dict[str, list[SupplierOffer]] = {}
    for link in suppliers["part_suppliers"]:
        offers.setdefault(link["part_ref"], []).append(
            SupplierOffer(link["supplier_id"], Decimal(link["price_multiplier"]), link["is_default"])
        )
    plants = {
        s["supplier_id"]: tuple(
            Plant(p["plant_id"], s["supplier_id"], p["origin_country"], Decimal(p["price_coefficient"]),
                  Decimal(p["transport_co2_kg_per_kg"]), p["is_default"], p["label"], p["lead_time_days"])
            for p in s["plants"]
        )
        for s in suppliers["suppliers"]
    }
    return Sourcing({ref: tuple(o) for ref, o in offers.items()}, plants)


def reference_snapshot(version: str = MULTIPLA) -> PriceSnapshot:
    prices = {
        row["part_ref"]: Decimal(row["base_price_eur"]) / Decimal(row["price_per"])
        for row in read_seeds(SEEDS)["parts"]
        if row["base_price_eur"]
    }
    return PriceSnapshot(f"snap-ref-{version}", TAKEN_AT, "EUR", "reference", prices, bom_version=version)


def mockup_bytes() -> bytes:
    return (SEEDS / "body_multipla.glb").read_bytes()
