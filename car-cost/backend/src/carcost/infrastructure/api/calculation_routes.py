"""Scénarios et calculs.

Ces routes ne décident de rien : elles lisent, appellent un cas d'usage, et
sérialisent. Le total, la décomposition, la portée d'un paramètre et l'état
d'obsolescence viennent tous de la couche application — le navigateur ne
recalcule jamais (ADR-0009).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import FastAPI, Query, Request
from pydantic import BaseModel, Field

from ...application.browse_bom import where_used
from ...application.calculation_state import scope_label, state_of
from ...application.price_resolution import (
    ParameterNotApplicable,
    PlantNotAvailableForSupplier,
    PriceOverrideNeedsJustification,
    resolve_unit_prices,
)
from ...application.run_calculation import run_calculation, with_contributors
from ...application.scenario import Scenario, ScenarioParameter
from .errors import error_response

SCALE = Decimal("0.000001")


class NoPriceSnapshot(Exception):
    """Aucun snapshot, même périmé : rien ne peut être calculé."""


class NewScenario(BaseModel):
    bom_version: str
    name: str
    display_currency: str = "EUR"
    labour_rate: Decimal
    active_rules: list[str] = Field(default_factory=lambda: ["labour"])


class NewParameter(BaseModel):
    scope: str = "part"
    path: str | None = None
    supplier_id: str | None = None
    plant_id: str | None = None
    price_override: Decimal | None = None
    price_override_justification: str | None = None
    labour_minutes: Decimal | None = None


class NewCalculation(BaseModel):
    scenario_id: str
    price_snapshot_id: str | None = None


def register_calculation_routes(app: FastAPI, repositories) -> None:
    @app.exception_handler(ParameterNotApplicable)
    async def _not_applicable(_: Request, error: ParameterNotApplicable):
        return error_response(422, "PARAMETER_NOT_APPLICABLE", str(error))

    @app.exception_handler(PlantNotAvailableForSupplier)
    async def _wrong_plant(_: Request, error: PlantNotAvailableForSupplier):
        return error_response(422, "PLANT_NOT_AVAILABLE_FOR_SUPPLIER", str(error))

    @app.exception_handler(PriceOverrideNeedsJustification)
    async def _needs_justification(_: Request, error: PriceOverrideNeedsJustification):
        return error_response(
            422, "PRICE_OVERRIDE_JUSTIFICATION_REQUIRED", str(error)
        )

    @app.exception_handler(NoPriceSnapshot)
    async def _no_snapshot(_: Request, error: NoPriceSnapshot):
        return error_response(409, "NO_PRICE_SNAPSHOT", str(error))

    @app.post("/api/v1/scenarios", status_code=201)
    def create_scenario(payload: NewScenario):
        scenario = Scenario(
            id=f"scn-{uuid.uuid4().hex[:12]}",
            bom_version=payload.bom_version,
            display_currency=payload.display_currency,
            labour_rate=payload.labour_rate,
            active_rules=frozenset(payload.active_rules),
        )
        repositories.scenarios.create(scenario)
        return _scenario_payload(repositories, scenario)

    @app.get("/api/v1/scenarios/{scenario_id}")
    def read_scenario(scenario_id: str):
        return _scenario_payload(
            repositories, repositories.scenarios.get(scenario_id)
        )

    @app.put("/api/v1/scenarios/{scenario_id}/parameters/{target}")
    def put_parameter(scenario_id: str, target: str, payload: NewParameter):
        scenario = repositories.scenarios.get(scenario_id)
        bom = repositories.bom.load(scenario.bom_version)

        part_ref = target.split("/")[-1]
        parameter = ScenarioParameter(
            part_ref=part_ref,
            scope=payload.scope,
            path=target if payload.scope == "path" else None,
            supplier_id=payload.supplier_id,
            plant_id=payload.plant_id,
            price_override=payload.price_override,
            price_override_justification=payload.price_override_justification,
            labour_minutes=payload.labour_minutes,
        )

        # On valide avant d'écrire : un paramètre refusé ne doit pas laisser de
        # trace, sinon l'écran afficherait un réglage qui n'a jamais pris.
        candidate = _with_parameter(scenario, parameter)
        snapshot = _snapshot_or_none(repositories)
        if snapshot is not None:
            resolve_unit_prices(
                bom, repositories.sourcing.load(scenario.bom_version), snapshot,
                candidate,
            )

        parameter_id = repositories.scenarios.put_parameter(scenario_id, parameter)
        occurrences = where_used(bom, part_ref, limit=1).total
        state, reason = _state(repositories, repositories.scenarios.get(scenario_id))

        return {
            "parameter_id": parameter_id,
            "scope": parameter.scope,
            "part_ref": part_ref,
            "affects_occurrences": occurrences,
            "scope_label": scope_label(parameter.scope, occurrences=occurrences),
            "calculation_state": state.value,
            "stale_reason": reason,
        }

    @app.delete("/api/v1/scenarios/{scenario_id}/parameters/{parameter_id}")
    def delete_parameter(scenario_id: str, parameter_id: str):
        repositories.scenarios.delete_parameter(scenario_id, parameter_id)
        state, reason = _state(repositories, repositories.scenarios.get(scenario_id))
        return {"calculation_state": state.value, "stale_reason": reason}

    @app.post("/api/v1/calculations", status_code=201)
    def create_calculation(payload: NewCalculation):
        scenario = repositories.scenarios.get(payload.scenario_id)
        bom = repositories.bom.load(scenario.bom_version)
        sourcing = repositories.sourcing.load(scenario.bom_version)
        snapshot = _snapshot(repositories, payload.price_snapshot_id)

        resolved = resolve_unit_prices(bom, sourcing, snapshot, scenario)
        calculation = run_calculation(
            bom=bom,
            scenario=scenario,
            snapshot=snapshot,
            resolved=resolved,
            now=repositories.clock(),
            calculation_id=f"calc-{uuid.uuid4().hex[:12]}",
        )
        repositories.calculations.save(calculation)
        return _calculation_payload(calculation)

    @app.get("/api/v1/calculations/{calculation_id}")
    def read_calculation(calculation_id: str):
        calculation = repositories.calculations.get(calculation_id)
        if not calculation.top_contributors:
            calculation = with_contributors(
                calculation, repositories.bom.load(calculation.bom_version)
            )
        return _calculation_payload(calculation)

    @app.get("/api/v1/calculations/{calculation_id}/aggregated")
    def read_aggregated(
        calculation_id: str,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        calculation = repositories.calculations.get(calculation_id)
        priced = [line for line in calculation.lines if line.own_contribution is not None]
        window = priced[offset : offset + limit]
        return {
            "items": [_line_payload(line, calculation) for line in window],
            "total": len(priced),
            "limit": limit,
            "offset": offset,
            # Sur l'ensemble des pièces, pas sur la page : c'est la valeur que
            # le test d'invariant compare au total.
            "sum_of_own_contributions": _money(
                sum((line.own_contribution for line in priced), Decimal(0)),
                calculation.display_currency,
            ),
        }


# ---------------------------------------------------------------- assemblage


def _with_parameter(scenario: Scenario, parameter: ScenarioParameter) -> Scenario:
    from dataclasses import replace

    kept = tuple(
        existing
        for existing in scenario.parameters
        if not (
            existing.part_ref == parameter.part_ref
            and existing.scope == parameter.scope
            and (existing.path or "") == (parameter.path or "")
        )
    )
    return replace(scenario, parameters=kept + (parameter,))


def _snapshot_or_none(repositories):
    return repositories.snapshots.latest() if repositories.snapshots else None


def _snapshot(repositories, snapshot_id: str | None):
    if snapshot_id is not None:
        return repositories.snapshots.get(snapshot_id)
    snapshot = _snapshot_or_none(repositories)
    if snapshot is None:
        raise NoPriceSnapshot(
            "aucun snapshot de prix, même périmé : prenez-en un avant de calculer"
        )
    return snapshot


def _state(repositories, scenario: Scenario):
    latest = repositories.calculations.latest_for(scenario.id)
    return state_of(
        scenario,
        _snapshot_or_none(repositories),
        last_digest=latest.input_digest if latest else None,
        last_snapshot_id=latest.snapshot_id if latest else None,
    )


def _money(amount: Decimal, currency: str) -> dict:
    """Le montant exact, tel quel.

    L'arrondir ici casserait l'addition : dix montants arrondis ne somment pas
    au total arrondi. L'arrondi est un acte d'affichage, et il a lieu dans le
    navigateur (ADR-0011).
    """
    return {"amount": str(amount), "currency": currency}


def _scenario_payload(repositories, scenario: Scenario) -> dict:
    state, reason = _state(repositories, scenario)
    return {
        "id": scenario.id,
        "bom_version": scenario.bom_version,
        "display_currency": scenario.display_currency,
        "labour_rate": str(scenario.labour_rate),
        "active_rules": sorted(scenario.active_rules),
        "parameters": [
            {
                "part_ref": parameter.part_ref,
                "scope": parameter.scope,
                "path": parameter.path,
                "supplier_id": parameter.supplier_id,
                "plant_id": parameter.plant_id,
                "price_override": (
                    str(parameter.price_override)
                    if parameter.price_override is not None
                    else None
                ),
                "price_override_justification": parameter.price_override_justification,
            }
            for parameter in scenario.parameters
        ],
        "calculation_state": state.value,
        "stale_reason": reason,
    }


def _calculation_payload(calculation) -> dict:
    currency = calculation.display_currency
    return {
        "id": calculation.id,
        "scenario_id": calculation.scenario_id,
        "status": calculation.status.value,
        "bom_version": calculation.bom_version,
        "engine_version": calculation.engine_version,
        "rules_version": calculation.rules_version,
        "active_rules": list(calculation.active_rules),
        "computed_at": calculation.computed_at.isoformat(),
        "input_digest": calculation.input_digest,
        "display_currency": currency,
        "total_cost": _money(calculation.total_cost, currency),
        "price_snapshot": {
            "id": calculation.snapshot_id,
            "age_seconds": int(calculation.snapshot_age.total_seconds()),
            "status": calculation.snapshot_status,
        },
        "systems": [
            {
                "system": system.system,
                "cost": _money(system.cost, currency),
                "cost_share_pct": str(system.share_pct),
            }
            for system in calculation.systems
        ],
        "top_cost_contributors": [
            {
                "part_ref": contributor.part_ref,
                "label": contributor.label,
                "system": contributor.system,
                "cumulative_quantity": str(contributor.cumulative_quantity),
                "own_contribution": _money(contributor.own_contribution, currency),
                "share_pct": str(contributor.share_pct),
                "first_path": contributor.first_path,
            }
            for contributor in calculation.top_contributors
        ],
        "parts_without_price": list(calculation.parts_without_price),
        # Compté ici plutôt que dans le navigateur : chaque ligne relève d'une
        # seule catégorie, et c'est le serveur qui sait laquelle.
        "issue_counts": calculation.issue_counts(),
    }


def _line_payload(line, calculation) -> dict:
    currency = calculation.display_currency
    explanation = calculation.explanations.get(line.part_ref)
    payload = {
        "part_ref": line.part_ref,
        "cumulative_quantity": str(line.cumulative_quantity),
        "occurrence_count": line.occurrence_count,
        "own_unit_cost": _money(line.own_unit_cost, currency),
        "own_contribution": _money(line.own_contribution, currency),
        "unit_cost": (
            _money(line.full_unit_cost, currency)
            if line.full_unit_cost is not None
            else None
        ),
    }
    if explanation is not None:
        payload["price_source"] = {
            "supplier_id": explanation.supplier_id,
            "plant_id": explanation.plant_id,
            "origin_country": explanation.origin_country,
            "is_overridden": explanation.is_overridden,
        }
    return payload
