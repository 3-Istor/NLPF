"""Snapshots de calcul : un calcul figé sous un nom (ADR-0014).

Ces routes lisent, appellent le cas d'usage et sérialisent. Aucune ne recalcule
un calcul figé : comparer deux gels relit les calculs enregistrés.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import FastAPI, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...application import freeze_calculation, manage_scenarios
from ...application.ports import (
    CalculationSnapshotNotFound,
    SnapshotNameTaken,
)
from ...domain.calculation_snapshot import CalculationSnapshot, InvalidSnapshotName
from .calculation_routes import (
    _comparison_payload,
    _execute_calculation,
    _snapshot,
)
from .errors import error_response

_TAG = "Snapshots de calcul"


class NewCalculationSnapshot(BaseModel):
    scenario_id: str = Field(
        description="Identifiant `scn-…` du scénario à calculer puis figer.",
        examples=["scn-123456789abc"],
    )
    name: str = Field(
        description="Nom du gel, unique dans la version de nomenclature (sans casse ni accents).",
        examples=["Référence T3"],
    )


class RenameCalculationSnapshot(BaseModel):
    """Le nom seul : tout autre champ est refusé."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Nouveau nom.", examples=["Gel retenu"])


class CompareCalculationSnapshots(BaseModel):
    snapshot_a_id: str = Field(description="Gel de référence `csn-…`.")
    snapshot_b_id: str = Field(description="Gel comparé `csn-…`.")


def register_calculation_snapshot_routes(app: FastAPI, repositories) -> None:
    @app.exception_handler(InvalidSnapshotName)
    async def _invalid_name(_: Request, error: InvalidSnapshotName):
        return error_response(422, "INVALID_SNAPSHOT_NAME", str(error))

    @app.exception_handler(SnapshotNameTaken)
    async def _name_taken(_: Request, error: SnapshotNameTaken):
        return error_response(
            409, "SNAPSHOT_NAME_TAKEN", str(error),
            {"name": error.name, "existing_id": error.existing_id},
        )

    @app.exception_handler(CalculationSnapshotNotFound)
    async def _not_found(_: Request, error: CalculationSnapshotNotFound):
        return error_response(404, "CALCULATION_SNAPSHOT_NOT_FOUND", str(error))

    @app.exception_handler(manage_scenarios.ScenarioHasSnapshots)
    async def _has_snapshots(_: Request, error: manage_scenarios.ScenarioHasSnapshots):
        return error_response(
            409, "SCENARIO_HAS_SNAPSHOTS", str(error),
            {"snapshots": list(error.names)},
        )

    @app.post(
        "/api/v1/calculation-snapshots", status_code=201, tags=[_TAG],
        summary="Figer un calcul sous un nom",
        description=(
            "Lance le calcul du scénario avec ses réglages courants et le snapshot "
            "de prix le plus récent, puis le fige avec une copie des hypothèses."
        ),
    )
    def freeze(payload: NewCalculationSnapshot):
        def calculate(scenario):
            price_snapshot = _snapshot(repositories, None)
            return _execute_calculation(
                repositories, scenario.id, price_snapshot, scenario
            )

        snapshot = freeze_calculation.freeze_scenario(
            payload.scenario_id, payload.name,
            scenarios=repositories.scenarios,
            boms=repositories.bom,
            snapshots_repo=repositories.calculation_snapshots,
            calculate=calculate,
            snapshot_id=f"csn-{uuid.uuid4().hex[:12]}",
            now=repositories.clock(),
        )
        return _full_payload(repositories, snapshot)

    @app.get(
        "/api/v1/calculation-snapshots", tags=[_TAG],
        summary="Lister les snapshots de calcul d'une version",
        description="Du plus récent au plus ancien.",
    )
    def list_snapshots(
        bom_version: Annotated[
            str, Query(description="Version de nomenclature (obligatoire).")
        ],
    ):
        items = repositories.calculation_snapshots.list_for(bom_version)
        return {
            "items": [_summary_payload(item) for item in items],
            "total": len(items),
        }

    @app.post(
        "/api/v1/calculation-snapshots/compare", tags=[_TAG],
        summary="Comparer deux snapshots de calcul",
        description=(
            "Compare les calculs figés tels quels : aucun calcul n'est relancé ni "
            "enregistré. Le delta vaut B moins A."
        ),
    )
    def compare(payload: CompareCalculationSnapshots):
        comparison, snapshot_a, snapshot_b = freeze_calculation.compare_snapshots(
            payload.snapshot_a_id, payload.snapshot_b_id,
            snapshots_repo=repositories.calculation_snapshots,
            calculations=repositories.calculations,
        )
        return {
            **_comparison_payload(comparison),
            "snapshot_a": {"id": snapshot_a.id, "name": snapshot_a.name},
            "snapshot_b": {"id": snapshot_b.id, "name": snapshot_b.name},
        }

    @app.get(
        "/api/v1/calculation-snapshots/{snapshot_id}", tags=[_TAG],
        summary="Lire un snapshot de calcul",
    )
    def read(
        snapshot_id: Annotated[
            str, Path(description="Identifiant `csn-…`.", examples=["csn-123456789abc"])
        ],
    ):
        return _full_payload(
            repositories, repositories.calculation_snapshots.get(snapshot_id)
        )

    @app.patch(
        "/api/v1/calculation-snapshots/{snapshot_id}", tags=[_TAG],
        summary="Renommer un snapshot de calcul",
        description="Le nom est le seul champ qui change ; l'ancien nom reste dans l'historique.",
    )
    def rename(
        snapshot_id: Annotated[str, Path(description="Identifiant `csn-…`.")],
        payload: RenameCalculationSnapshot,
    ):
        snapshot = freeze_calculation.rename_snapshot(
            snapshot_id, payload.name,
            snapshots_repo=repositories.calculation_snapshots,
            now=repositories.clock(),
        )
        return _full_payload(repositories, snapshot)


def _summary_payload(snapshot: CalculationSnapshot) -> dict:
    return {
        "id": snapshot.id,
        "name": snapshot.name,
        "bom_version": snapshot.bom_version,
        "scenario_id": snapshot.scenario_id,
        "scenario_name": snapshot.scenario_name,
        "calculation_id": snapshot.calculation_id,
        "price_snapshot_id": snapshot.price_snapshot_id,
        "created_at": snapshot.created_at.isoformat(),
    }


def _full_payload(repositories, snapshot: CalculationSnapshot) -> dict:
    history = repositories.calculation_snapshots.name_history(snapshot.id)
    return {
        **_summary_payload(snapshot),
        "display_currency": snapshot.display_currency,
        "labour_rate": str(snapshot.labour_rate),
        "active_rules": sorted(snapshot.active_rules),
        "parameters": [
            {
                "part_ref": parameter.part_ref,
                "scope": parameter.scope,
                "path": parameter.path,
                "supplier_id": parameter.supplier_id,
                "plant_id": parameter.plant_id,
                "purchase_currency": parameter.purchase_currency,
                "labour_minutes": (
                    str(parameter.labour_minutes)
                    if parameter.labour_minutes is not None
                    else None
                ),
                "price_override": (
                    str(parameter.price_override)
                    if parameter.price_override is not None
                    else None
                ),
                "price_override_justification": parameter.price_override_justification,
            }
            for parameter in snapshot.parameters
        ],
        "name_history": [
            {"name": name, "renamed_at": renamed_at.isoformat()}
            for name, renamed_at in history
        ],
    }
