"""Import d'une variante de carrosserie, modèle 3D et écarts (ADR-0017).

Les routes lisent le corps brut, appellent `import_body` ou `body_changes` et
sérialisent leur résultat : aucune règle, aucun calcul. Montants et masses
partent en chaînes décimales (ADR-0011).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from threading import Lock

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool

from ...application.body_import import BodyImportRejected
from ...application.body_model import ModelFileRejected
from ...application.import_body import IncompletePrices, body_changes, import_body
from ...application.ports import ModelNotFound, VariantIdCollision
from ..gltf_reader import read_glb
from .errors import error_response

_MESSAGES = {
    "CREATED": "variante créée",
    "ALREADY_IMPORTED": "déjà importé",
    "NO_CHANGE": "aucun changement",
}
# Deux imports du même fichier au même instant ne doivent créer qu'un scénario.
# ponytail: verrou de processus ; plusieurs workers demanderaient un verrou consultatif Postgres.
_IMPORT = Lock()


def register_body_routes(app: FastAPI, repositories) -> None:
    @app.exception_handler(ModelNotFound)
    async def _no_model(_: Request, error: ModelNotFound):
        return error_response(404, "MODEL_NOT_FOUND", f"{error} n'a pas de modèle 3D")

    @app.exception_handler(VariantIdCollision)
    async def _collision(_: Request, error: VariantIdCollision):
        return error_response(409, "VARIANT_ID_COLLISION", str(error))

    @app.exception_handler(IncompletePrices)
    async def _incomplete(_: Request, error: IncompletePrices):
        return error_response(
            409, "INCOMPLETE_CALCULATION", str(error),
            {"parts_without_price": list(error.parts_without_price), "snapshot_id": error.snapshot_id},
        )

    @app.exception_handler(BodyImportRejected)
    async def _rejected(_: Request, error: BodyImportRejected):
        faults = [
            {"code": f.code, "message": f.message, "object": f.object_name, "part_ref": f.part_ref}
            for f in error.faults
        ]
        return error_response(422, "BODY_IMPORT_REJECTED", str(error), {"faults": faults})

    @app.exception_handler(ModelFileRejected)
    async def _unreadable(_: Request, error: ModelFileRejected):
        fault = {"code": error.code, "message": error.message, "object": None, "part_ref": None}
        return error_response(422, "BODY_IMPORT_REJECTED", error.message, {"faults": [fault]})

    def _import(version: str, data: bytes):
        with _IMPORT:
            return import_body(
                version, data, read_model=read_glb, boms=repositories.bom, models=repositories.models,
                variants=repositories.variants, sourcing=repositories.sourcing,
                snapshots=repositories.snapshots, scenarios=repositories.scenarios,
                calculations=repositories.calculations, clock=repositories.clock,
                new_id=lambda: uuid.uuid4().hex[:12],
            )

    @app.post("/api/v1/bom/{version}/body-imports")
    async def create_body_import(version: str, request: Request, response: Response):
        """Importe un `.glb` (corps brut) : une variante chiffrée, ou rien."""
        outcome = await run_in_threadpool(_import, version, await request.body())
        response.status_code = 201 if outcome.status == "CREATED" else 200
        return {
            "status": outcome.status,
            "message": _MESSAGES[outcome.status],
            "parent_version": outcome.parent_version,
            "variant": (
                {"id": outcome.variant_id, "label": outcome.variant_label} if outcome.variant_id else None
            ),
            "scenario_id": outcome.scenario_id,
            **_changes_payload(outcome),
        }

    @app.get("/api/v1/bom/{version}/model")
    def read_model(version: str):
        stored = repositories.models.get(version)
        if stored is None:
            raise ModelNotFound(version)
        return Response(stored.glb, media_type="model/gltf-binary")

    @app.get("/api/v1/bom/{version}/body-changes")
    def read_body_changes(version: str):
        changes = body_changes(
            version, boms=repositories.bom, sourcing=repositories.sourcing,
            snapshots=repositories.snapshots, clock=repositories.clock,
        )
        return {"version": changes.version, "parent_version": changes.parent_version, **_changes_payload(changes)}


def _changes_payload(result) -> dict:
    return {
        "changes": [
            {
                "part_ref": c.part_ref,
                "label": c.label,
                "kind": c.kind,
                "material_before": c.material_before,
                "material_after": c.material_after,
                "mass_before_kg": _text(c.mass_before_kg),
                "mass_after_kg": str(c.mass_after_kg),
                "mass_delta_kg": str(c.mass_delta_kg),
                "cumulative_quantity": str(c.cumulative_quantity),
                "unit_cost_before": _text(c.unit_cost_before),
                "unit_cost_after": _text(c.unit_cost_after),
            }
            for c in result.changes
        ],
        "material_mass_delta_kg": str(result.material_mass_delta_kg),
        "cost": (
            None if result.cost is None else {
                "snapshot_id": result.cost.snapshot_id,
                "total_before": _money(result.cost.total_before),
                "total_after": _money(result.cost.total_after),
                "delta": _money(result.cost.delta),
            }
        ),
        "cost_status": result.cost_status,
    }


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _money(amount: Decimal) -> dict:
    # Un écart nul s'écrit « 0 », pas « 0E-12 » ; l'import chiffre toujours en euros.
    return {"amount": str(amount or Decimal(0)), "currency": "EUR"}
