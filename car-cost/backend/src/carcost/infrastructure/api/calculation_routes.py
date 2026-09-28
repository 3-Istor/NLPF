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
from ...application.calculation_issues import calculation_issues
from ...application.calculation_state import scope_label, state_of
from ...application.explain_calculation import (
    AssemblyBreakdown,
    CatalogueBreakdown,
    LineExplanation,
    OverrideBreakdown,
    explain_line,
)
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

    @app.get("/api/v1/calculations/{calculation_id}/explain")
    def read_explanation(
        calculation_id: str,
        path: str = Query(..., description="La ligne à expliquer, chemin complet"),
    ):
        calculation = repositories.calculations.get(calculation_id)
        explanation = explain_line(
            calculation=calculation,
            bom=repositories.bom.load(calculation.bom_version),
            scenario=repositories.scenarios.get(calculation.scenario_id),
            snapshot=repositories.snapshots.get(calculation.snapshot_id),
            sourcing=repositories.sourcing.load(calculation.bom_version),
            path=path,
        )
        return _explanation_payload(explanation, calculation.display_currency)

    @app.get("/api/v1/calculations/{calculation_id}/issues")
    def read_issues(
        calculation_id: str,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        calculation = repositories.calculations.get(calculation_id)
        issues = calculation_issues(
            calculation, repositories.bom.load(calculation.bom_version)
        )
        return {
            "items": [
                {
                    "kind": issue.kind,
                    "part_ref": issue.part_ref,
                    "label": issue.label,
                    "system": issue.system,
                    "path": issue.path,
                    "cumulative_quantity": _decimal(issue.cumulative_quantity),
                    "occurrence_count": issue.occurrence_count,
                }
                for issue in issues[offset : offset + limit]
            ],
            "total": len(issues),
            "limit": limit,
            "offset": offset,
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


#: Ce que dit `price_source.reason` pour chaque statut de ligne.
PRICE_REASONS = {
    "OK": None,
    "FALLBACK": "Absent de la réponse de l'API : dernier prix connu retenu",
    "QUARANTINED": (
        "Valeur refusée (journal de quarantaine) : dernier prix sain retenu"
    ),
    "MISSING": "Aucun prix connu, ni frais ni ancien : le total est partiel",
}


def _explanation_payload(explanation: LineExplanation, currency: str) -> dict:
    parameter = explanation.applied_parameter
    status = explanation.price_status
    return {
        "path": explanation.path,
        "part_ref": explanation.part_ref,
        "valuation_mode": explanation.valuation_mode,
        "unit_cost_breakdown": _breakdown_payload(explanation.breakdown, currency),
        "quantity": {
            "on_path": _decimal(explanation.quantity_on_path),
            "cumulative_in_vehicle": _decimal(explanation.cumulative_quantity),
            "unit": explanation.unit,
        },
        "occurrence_count": explanation.occurrence_count,
        "applied_parameter": (
            None
            if parameter is None
            else {
                "scope": parameter.scope,
                "scope_label": scope_label(
                    parameter.scope, occurrences=explanation.occurrence_count
                ),
                "supplier_id": parameter.supplier_id,
                "plant_id": parameter.plant_id,
                "price_override": _optional_money(parameter.price_override, currency),
            }
        ),
        "parameters_changed_since_calculation": explanation.parameters_changed_since,
        "applied_rules": list(explanation.applied_rules),
        "price_source": {
            "snapshot_id": explanation.snapshot_id,
            "status": status,
            # La date d'un prix de repli est celle du snapshot qui l'a repris,
            # pas celle du prix : on ne la donne pas plutôt que de la donner
            # fausse. Remonter la chaîne des replis reste à faire.
            "as_of": (
                explanation.snapshot_taken_at.isoformat()
                if status in ("OK", None)
                else None
            ),
            "reason": PRICE_REASONS.get(status),
        },
    }


def _breakdown_payload(breakdown, currency: str) -> dict | None:
    if breakdown is None:
        return None
    if isinstance(breakdown, CatalogueBreakdown):
        factors = (
            breakdown.reference_price,
            breakdown.supplier_multiplier,
            breakdown.plant_coefficient,
        )
        return {
            "kind": "catalogue",
            "reference_price": _money(breakdown.reference_price, currency),
            "supplier": {
                "supplier_id": breakdown.supplier_id,
                "name": breakdown.supplier_name,
                "multiplier": _optional_decimal(breakdown.supplier_multiplier),
            },
            "plant": {
                "plant_id": breakdown.plant_id,
                "origin": breakdown.origin_country,
                "coefficient": _optional_decimal(breakdown.plant_coefficient),
            },
            "formula": (
                " × ".join(_decimal(factor) for factor in factors)
                if None not in factors
                else None
            ),
            "unit_cost": _money(breakdown.unit_cost, currency),
            # Faux si le sourcing a changé depuis le calcul : la formule ne
            # redonne plus le prix enregistré, et l'écran doit le dire.
            "reproduced": breakdown.reproduced,
        }
    if isinstance(breakdown, OverrideBreakdown):
        return {
            "kind": "override",
            "unit_cost": _money(breakdown.unit_cost, currency),
            "justification": breakdown.justification,
        }
    assert isinstance(breakdown, AssemblyBreakdown)
    return {
        "kind": "assembly",
        "children": [
            {
                "part_ref": child.part_ref,
                "quantity": _decimal(child.quantity),
                "unit_cost": _optional_money(child.unit_cost, currency),
                "contribution": _optional_money(child.contribution, currency),
            }
            for child in breakdown.children
        ],
        "children_cost": _optional_money(breakdown.children_cost, currency),
        "labour": {
            "labour_minutes": _optional_decimal(breakdown.labour_minutes),
            "labour_rate": _money(breakdown.labour_rate, currency),
            "amount": _optional_money(breakdown.labour_cost, currency),
        },
        "unit_cost": _optional_money(breakdown.unit_cost, currency),
    }


def _optional_money(amount: Decimal | None, currency: str) -> dict | None:
    return None if amount is None else _money(amount, currency)


def _decimal(value: Decimal) -> str:
    return str(value.quantize(SCALE))


def _optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else _decimal(value)
