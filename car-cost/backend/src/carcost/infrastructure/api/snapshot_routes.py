"""Les snapshots de prix, vus depuis l'écran.

Le journal de quarantaine existait en base ; sans cette route, il n'existait que
pour qui ouvre `psql`. Un prix refusé puis remplacé doit pouvoir se lire là où
l'on regarde le total, sinon le repli est silencieux (ADR-0003, mode de panne P2).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Path, Request

from ...application.ports import PriceSnapshotNotFound
from .errors import error_response


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
    def list_snapshots():
        snapshots = repositories.snapshots.list_all()
        now = repositories.clock()
        return {
            "items": [
                {
                    "id": snapshot.id,
                    "taken_at": snapshot.taken_at.isoformat(),
                    "source": snapshot.source,
                    "currency": snapshot.currency,
                    "status": snapshot.status(now).value,
                    "age_seconds": int(snapshot.age(now).total_seconds()),
                    "counts": {
                        "prices": len(snapshot.prices),
                        "fallback": len(snapshot.fallback_refs),
                        "quarantined": len(snapshot.quarantined_refs),
                        "missing": len(snapshot.missing_refs),
                    },
                }
                for snapshot in snapshots
            ],
            "total": len(snapshots),
        }

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
                examples=["snp-7a9947ddac59"],
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
