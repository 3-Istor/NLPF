"""Prendre un snapshot de prix et l'enregistrer.

    python -m carcost.infrastructure.snapshot_cli [--fail timeout]

Interroge l'API de prix pour toutes les pièces achetées de la nomenclature, et
écrit le snapshot. En cas de silence de l'API, le dernier snapshot valide reste
en vigueur et la commande le dit — elle n'en fabrique pas un daté d'aujourd'hui
avec les prix d'hier.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone

from ..application.take_snapshot import NoPriceAvailable, TookFallback, take_snapshot
from .http_price_source import HttpPriceSource
from .postgres_bom_repository import PostgresBomRepository
from .postgres_repositories import PostgresPriceSnapshotRepository

DEFAULT_DSN = "postgresql://3istor:3istor@127.0.0.1:5432/3istor"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("CARCOST_DSN", DEFAULT_DSN))
    parser.add_argument(
        "--api", default=os.environ.get("CARCOST_PRICE_API", "http://127.0.0.1:8099")
    )
    parser.add_argument("--bom-version", default="bom-multipla-2026-09-22")
    parser.add_argument("--currency", default="EUR")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument(
        "--fail", default="none", choices=["none", "timeout", "outlier", "garbage", "missing"],
        help="provoque une panne de l'API, pour la démonstration",
    )
    arguments = parser.parse_args(argv)

    bom = PostgresBomRepository(arguments.dsn).load(arguments.bom_version)
    purchased = sorted(ref for ref, part in bom.parts.items() if part.is_purchased)

    snapshots = PostgresPriceSnapshotRepository(arguments.dsn)
    previous = snapshots.latest()
    source = HttpPriceSource(
        arguments.api,
        timeout_seconds=arguments.timeout,
        failure_mode=arguments.fail,
    )

    try:
        outcome = take_snapshot(
            source,
            refs=purchased,
            currency=arguments.currency,
            previous=previous,
            now=datetime.now(timezone.utc),
            snapshot_id=f"snp-{uuid.uuid4().hex[:12]}",
        )
    except NoPriceAvailable as refusal:
        print(f"refus : {refusal}", file=sys.stderr)
        return 1

    if isinstance(outcome, TookFallback):
        age = outcome.snapshot.age(datetime.now(timezone.utc))
        print(
            f"repli : {outcome.reason}. Le snapshot {outcome.snapshot.id} "
            f"(âge {int(age.total_seconds() // 60)} min) reste en vigueur ; "
            f"les calculs qui l'utiliseront seront marqués dégradés."
        )
        return 0

    snapshots.save(
        outcome.snapshot,
        quarantined=outcome.quarantined,
        previous_id=previous.id if previous else None,
    )
    print(
        f"snapshot {outcome.snapshot.id} enregistré : "
        f"{len(outcome.snapshot.prices)} prix en {arguments.currency}"
    )
    for entry in outcome.quarantined:
        print(
            f"  quarantaine {entry.part_ref} : « {entry.rejected_value} » refusé "
            f"({entry.reason}) — retenu {entry.replacement}"
        )
    fallbacks = sorted(outcome.snapshot.fallback_refs)
    silent = [ref for ref in fallbacks
              if ref not in {e.part_ref for e in outcome.quarantined}]
    for ref in silent:
        # Une pièce absente de la réponse, remplacée par son dernier prix connu.
        # Ne pas l'annoncer ici serait un repli silencieux.
        print(f"  repli      {ref} : absent de la réponse, dernier prix connu retenu")
    for ref in outcome.missing:
        print(f"  sans prix  {ref} : aucun historique, la pièce est signalée")
    if outcome.quarantined or outcome.missing or fallbacks:
        print("  snapshot marqué dégradé ; les calculs qui l'utilisent le diront.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
