"""Choisir le sourcing le moins cher sous contraintes, pièce par pièce."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from ..domain.bom import Bom
from ..domain.prices import PriceSnapshot
from .price_resolution import resolve_purchase_price
from .run_calculation import Calculation, CalculationStatus
from .scenario import Plant, Scenario, ScenarioParameter, Sourcing, SupplierOffer
from .tree_view import path_quantity


class IncompleteBaseline(Exception):
    """Une économie ne peut pas être établie à partir d'un total incomplet."""


@dataclass(frozen=True)
class SourcingConstraints:
    forbidden_origins: frozenset[str] = frozenset()
    max_lead_time_days: int | None = None


@dataclass(frozen=True)
class SourcingRecommendation:
    part_ref: str
    current_supplier_id: str
    current_plant_id: str
    current_origin: str
    recommended_supplier_id: str
    recommended_plant_id: str
    recommended_origin: str
    recommended_lead_time_days: int
    current_unit_price: Decimal
    recommended_unit_price: Decimal
    affected_quantity: Decimal
    estimated_saving: Decimal
    parameter: ScenarioParameter
    #: L'option actuelle viole une contrainte : le changement est imposé, même
    #: s'il coûte plus cher (économie négative).
    required_by_constraint: bool = False


@dataclass(frozen=True)
class UnresolvedPart:
    """Une pièce dont le sourcing actuel viole une contrainte sans remède."""

    part_ref: str
    current_supplier_id: str
    current_plant_id: str
    current_origin: str
    reason: str


@dataclass(frozen=True)
class SourcingReport:
    recommendations: tuple[SourcingRecommendation, ...]
    #: Jamais omises : une variante créée sans elles garderait une provenance
    #: interdite sous un nom qui laisse croire le contraire.
    unresolved: tuple[UnresolvedPart, ...] = ()


def recommend(
    *,
    bom: Bom,
    sourcing: Sourcing,
    snapshot: PriceSnapshot,
    scenario: Scenario,
    baseline: Calculation,
    constraints: SourcingConstraints,
) -> SourcingReport:
    if baseline.status is CalculationStatus.INCOMPLETE:
        raise IncompleteBaseline(
            "recommandation impossible : un prix manquant ne peut pas être traité comme zéro"
        )
    recommendations = []
    unresolved = []
    for part_ref in sorted(bom.parts):
        if not bom.parts[part_ref].is_purchased:
            continue
        current_parameter = scenario.parameter_for(part_ref)
        if current_parameter is not None and current_parameter.price_override is not None:
            continue
        current = resolve_purchase_price(
            sourcing, snapshot, part_ref, current_parameter
        )
        if current is None or current.supplier_id is None or current.plant_id is None:
            continue
        current_plant = sourcing.plant(current.supplier_id, current.plant_id)
        if current_plant is None:
            continue

        candidates = _candidates(sourcing, part_ref, constraints)
        priced = []
        for offer, plant in candidates:
            parameter = ScenarioParameter(
                part_ref=part_ref,
                supplier_id=offer.supplier_id,
                plant_id=plant.plant_id,
                purchase_currency=(
                    current_parameter.purchase_currency
                    if current_parameter is not None
                    else None
                ),
            )
            explanation = resolve_purchase_price(
                sourcing, snapshot, part_ref, parameter
            )
            if explanation is not None:
                priced.append((explanation.unit_price, offer, plant, parameter))
        current_is_allowed = _plant_is_allowed(current_plant, constraints)
        if not priced:
            if not current_is_allowed:
                unresolved.append(
                    UnresolvedPart(
                        part_ref=part_ref,
                        current_supplier_id=current.supplier_id,
                        current_plant_id=current.plant_id,
                        current_origin=current_plant.origin_country,
                        reason=(
                            "le sourcing actuel viole une contrainte et aucune "
                            "option autorisée n'existe pour cette pièce"
                        ),
                    )
                )
            continue
        price, offer, plant, parameter = min(
            priced,
            key=lambda item: (item[0], item[1].supplier_id, item[2].plant_id),
        )
        if (
            price >= current.unit_price
            and current_is_allowed
        ):
            continue

        quantity = baseline.lines_by_ref[part_ref].cumulative_quantity
        quantity -= sum(
            path_quantity(bom, p.path)
            for p in scenario.parameters
            if p.part_ref == part_ref and p.scope == "path"
        )
        saving = quantity * (current.unit_price - price)
        recommendations.append(
            SourcingRecommendation(
                part_ref=part_ref,
                current_supplier_id=current.supplier_id,
                current_plant_id=current.plant_id,
                current_origin=current_plant.origin_country,
                recommended_supplier_id=offer.supplier_id,
                recommended_plant_id=plant.plant_id,
                recommended_origin=plant.origin_country,
                recommended_lead_time_days=plant.lead_time_days,
                current_unit_price=current.unit_price,
                recommended_unit_price=price,
                affected_quantity=quantity,
                estimated_saving=saving,
                parameter=parameter,
                required_by_constraint=not current_is_allowed,
            )
        )
    recommendations.sort(key=lambda item: (-item.estimated_saving, item.part_ref))
    return SourcingReport(
        recommendations=tuple(recommendations), unresolved=tuple(unresolved)
    )


def apply_recommendations(
    scenario: Scenario,
    recommendations: tuple[SourcingRecommendation, ...],
    accepted_part_refs: frozenset[str],
    *,
    scenario_id: str,
    name: str,
) -> Scenario:
    selected = {
        recommendation.part_ref: recommendation.parameter
        for recommendation in recommendations
        if recommendation.part_ref in accepted_part_refs
    }
    parameters = tuple(
        parameter
        for parameter in scenario.parameters
        if not (parameter.scope == "part" and parameter.part_ref in selected)
    ) + tuple(selected.values())
    return replace(
        scenario, id=scenario_id, name=name, parameters=parameters
    )


def _candidates(
    sourcing: Sourcing,
    part_ref: str,
    constraints: SourcingConstraints,
) -> tuple[tuple[SupplierOffer, Plant], ...]:
    forbidden = {origin.upper() for origin in constraints.forbidden_origins}
    candidates = []
    for offer in sourcing.offers_for(part_ref):
        for plant in sourcing.plants.get(offer.supplier_id, ()):
            if plant.origin_country.upper() in forbidden:
                continue
            if (
                constraints.max_lead_time_days is not None
                and plant.lead_time_days > constraints.max_lead_time_days
            ):
                continue
            candidates.append((offer, plant))
    return tuple(candidates)


def _plant_is_allowed(plant: Plant, constraints: SourcingConstraints) -> bool:
    if plant.origin_country.upper() in {
        origin.upper() for origin in constraints.forbidden_origins
    }:
        return False
    return not (
        constraints.max_lead_time_days is not None
        and plant.lead_time_days > constraints.max_lead_time_days
    )
