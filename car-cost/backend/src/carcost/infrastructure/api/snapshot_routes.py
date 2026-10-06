"""Les snapshots de prix, vus depuis l'écran.

Le journal de quarantaine existait en base ; sans cette route, il n'existait que
pour qui ouvre `psql`. Un prix refusé puis remplacé doit pouvoir se lire là où
l'on regarde le total, sinon le repli est silencieux (ADR-0003, mode de panne P2).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Path, Query, Request
from pydantic import BaseModel, Field

from ...application.ports import PriceSnapshotNotFound, PriceSourceError
from ...application.take_snapshot import TookFallback, new_snapshot_id, snapshot_for_bom
from .errors import error_response
from .price_source import previous_for, price_source


class NewPriceSnapshot(BaseModel):
    bom_version: str = Field(
        description="Nomenclature dont on fige les prix.",
        examples=["bom-valhalla-hybride-2026-10-05"],
    )
    currency: str = Field(default="EUR", description="Devise des prix demandés.")


def _summary(snapshot, now) -> dict:
    return {
        "id": snapshot.id,
        "taken_at": snapshot.taken_at.isoformat(),
        "source": snapshot.source,
        "currency": snapshot.currency,
        "bom_version": snapshot.bom_version,
        "status": snapshot.status(now).value,
        "age_seconds": int(snapshot.age(now).total_seconds()),
        "counts": {
            "prices": len(snapshot.prices),
            "fallback": len(snapshot.fallback_refs),
            "quarantined": len(snapshot.quarantined_refs),
            "missing": len(snapshot.missing_refs),
        },
    }


def register_snapshot_routes(app: FastAPI, repositories) -> None:
    @app.exception_handler(PriceSnapshotNotFound)
    async def _snapshot_not_found(_: Request, error: PriceSnapshotNotFound):
        return error_response(
            404, "PRICE_SNAPSHOT_NOT_FOUND", f"snapshot inconnu : {error.args[0]}"
        )

    @app.get(
        "/api/v1/price-snapshots", tags=["Prix"],
        summary="Lister les snapshots de prix",
        description=(
            "Retourne les snapshots du plus récent au plus ancien. Copiez l'identifiant `snp-…` "
            "du premier élément pour imposer ce snapshot, ou envoyez `null` dans les autres routes "
            "pour sélectionner automatiquement le plus récent."
        ),
    )
    def list_snapshots(
        bom_version: Annotated[
            str | None,
            Query(description="Seulement les snapshots de cette nomenclature (et les anciens, sans nomenclature)."),
        ] = None,
    ):
        snapshots = repositories.snapshots.list_all(bom_version)
        now = repositories.clock()
        return {
            "items": [_summary(snapshot, now) for snapshot in snapshots],
            "total": len(snapshots),
        }

    @app.post(
        "/api/v1/price-snapshots", status_code=201, tags=["Prix"],
        summary="Figer les prix actuels de l'API",
        description=(
            "Interroge l'API de prix pour toutes les pièces achetées de la nomenclature et "
            "enregistre un snapshot immuable, avec quarantaine et repli comme en ligne de "
            "commande. Si l'API ne répond pas, rien n'est créé : le dernier snapshot reste "
            "en vigueur (503 PRICE_SOURCE_UNAVAILABLE)."
        ),
    )
    def take_price_snapshot(payload: NewPriceSnapshot):
        source = price_source(repositories)
        bom = repositories.bom.load(payload.bom_version)
        previous = previous_for(repositories, payload.bom_version, payload.currency)
        now = repositories.clock()
        outcome = snapshot_for_bom(
            source, bom, bom_version=payload.bom_version, currency=payload.currency,
            previous=previous, now=now, snapshot_id=new_snapshot_id(now),
        )
        if isinstance(outcome, TookFallback):
            # Un snapshot daté d'aujourd'hui avec les prix d'hier ferait passer
            # des prix anciens pour frais (ADR-0003) : on n'en crée pas.
            raise PriceSourceError(
                f"{outcome.reason} ; le snapshot {outcome.snapshot.id} reste en vigueur"
            )
        repositories.snapshots.save(
            outcome.snapshot,
            quarantined=outcome.quarantined,
            previous_id=previous.id if previous else None,
        )
        return _summary(outcome.snapshot, now)

    @app.get(
        "/api/v1/price-snapshots/{snapshot_id}/quarantine", tags=["Prix"],
        summary="Lire le journal de quarantaine d'un snapshot",
        description="Explique les prix refusés et les éventuelles valeurs de remplacement.",
    )
    def read_quarantine(
        snapshot_id: Annotated[
            str,
            Path(
                description="Identifiant `snp-…` obtenu avec `GET /api/v1/price-snapshots`.",
                examples=["snp-2026-10-06-1923-7a9947"],
            ),
        ],
    ):
        records = repositories.snapshots.quarantine_of(snapshot_id)
        return {
            "snapshot_id": snapshot_id,
            "items": [
                {
                    "part_ref": record.part_ref,
                    "currency": record.currency,
                    "rejected_value": record.rejected_value,
                    "reason": record.reason,
                    # Absent de remplacement, la pièce est sans prix : `null`,
                    # jamais un zéro qui se lirait comme un prix.
                    "replacement": (
                        {"amount": str(record.replacement), "currency": record.currency}
                        if record.replacement is not None
                        else None
                    ),
                    "replacement_from_snapshot": record.replacement_from_snapshot,
                    "detected_at": record.detected_at.isoformat(),
                }
                for record in records
            ],
        }
