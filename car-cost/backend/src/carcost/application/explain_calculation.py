"""D'où vient le montant d'une ligne d'un calcul enregistré (docs/api.md §4.4).

Le calcul ne stocke que le fournisseur et l'usine retenus, pas les trois
facteurs du prix. On les relit dans le snapshot et le sourcing de la version,
tous deux figés (ADR-0003, ADR-0013), puis on **vérifie** qu'ils redonnent le
prix enregistré. Le coefficient d'usine, lui, n'est pas versionné : s'il a
changé depuis, `reproduced` le dit au lieu d'afficher une formule dont le
résultat n'est pas celui de la ligne.

Aucun montant n'est recalculé pour être affiché : les chiffres viennent des
lignes du calcul. Les facteurs ne servent qu'à les expliquer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ..domain.bom import Bom
from ..domain.prices import PriceSnapshot
from .browse_bom import PATH_SEPARATOR, PathNotFound
from .price_resolution import to_scale
from .run_calculation import Calculation, input_digest
from .scenario import Scenario, ScenarioParameter, Sourcing
from .tree_view import path_quantity


@dataclass(frozen=True)
class CatalogueBreakdown:
    """prix unitaire = référence × multiplicateur fournisseur × coefficient d'usine"""

    reference_price: Decimal
    supplier_id: str
    supplier_name: str
    supplier_multiplier: Decimal | None
    plant_id: str
    origin_country: str | None
    plant_coefficient: Decimal | None
    unit_cost: Decimal
    #: Les facteurs d'aujourd'hui redonnent-ils le prix enregistré ?
    reproduced: bool


@dataclass(frozen=True)
class OverrideBreakdown:
    unit_cost: Decimal
    #: None si le scénario a changé depuis : la justification d'alors n'est pas
    #: conservée avec le calcul.
    justification: str | None


@dataclass(frozen=True)
class ChildCost:
    part_ref: str
    quantity: Decimal
    unit_cost: Decimal | None
    contribution: Decimal | None


@dataclass(frozen=True)
class AssemblyBreakdown:
    children: tuple[ChildCost, ...]
    #: None si un enfant n'a pas de prix : le parent n'est pas « moins cher »,
    #: il est incalculable.
    children_cost: Decimal | None
    labour_minutes: Decimal | None
    labour_rate: Decimal
    labour_cost: Decimal | None
    unit_cost: Decimal | None


@dataclass(frozen=True)
class LineExplanation:
    path: str
    part_ref: str
    valuation_mode: str
    unit: str
    quantity_on_path: Decimal
    cumulative_quantity: Decimal
    occurrence_count: int
    breakdown: CatalogueBreakdown | OverrideBreakdown | AssemblyBreakdown | None
    #: None sur un ensemble fabriqué : il n'a pas de prix.
    price_status: str | None
    snapshot_id: str
    snapshot_taken_at: datetime
    applied_rules: tuple[str, ...]
    applied_parameter: ScenarioParameter | None
    #: Le scénario a changé depuis le calcul : on ne sait plus quel paramètre
    #: était en vigueur, et on ne fait pas passer l'actuel pour celui-là.
    parameters_changed_since: bool


def explain_line(
    *,
    calculation: Calculation,
    bom: Bom,
    scenario: Scenario,
    snapshot: PriceSnapshot,
    sourcing: Sourcing,
    path: str,
) -> LineExplanation:
    refs = path.split(PATH_SEPARATOR)
    if refs[0] != bom.root_ref:
        raise PathNotFound(f"{path} : un chemin part de la racine {bom.root_ref}")
    quantity_on_path = path_quantity(bom, path)
    ref = refs[-1]
    part = bom.parts[ref]
    line = next(line for line in calculation.lines if line.part_ref == ref)

    unchanged = input_digest(scenario, snapshot) == calculation.input_digest
    parameter = scenario.parameter_for(ref, path) if unchanged else None

    if part.is_purchased:
        breakdown = _purchase(calculation, ref, line.own_unit_cost, parameter,
                              snapshot, sourcing)
        price_status = calculation.price_status_of(ref).value
    else:
        breakdown = _assembly(calculation, bom, ref, path, scenario, unchanged)
        price_status = None

    return LineExplanation(
        path=path,
        part_ref=ref,
        valuation_mode=part.valuation_mode.value,
        unit=part.unit,
        quantity_on_path=quantity_on_path,
        cumulative_quantity=line.cumulative_quantity,
        occurrence_count=line.occurrence_count,
        breakdown=breakdown,
        price_status=price_status,
        snapshot_id=calculation.snapshot_id,
        snapshot_taken_at=snapshot.taken_at,
        applied_rules=calculation.active_rules,
        applied_parameter=parameter,
        parameters_changed_since=not unchanged,
    )


def _purchase(
    calculation: Calculation,
    ref: str,
    unit_cost: Decimal | None,
    parameter: ScenarioParameter | None,
    snapshot: PriceSnapshot,
    sourcing: Sourcing,
) -> CatalogueBreakdown | OverrideBreakdown | None:
    if unit_cost is None:
        return None

    recorded = calculation.explanations.get(ref)
    if recorded is not None and recorded.is_overridden:
        return OverrideBreakdown(unit_cost, recorded.override_justification)
    if recorded is None or recorded.supplier_id is None:
        # Relu en base, un prix forcé n'a ni fournisseur ni usine.
        justification = (
            parameter.price_override_justification
            if parameter is not None and parameter.price_override is not None
            else None
        )
        return OverrideBreakdown(unit_cost, justification)

    reference = snapshot.prices[ref]
    offer = sourcing.offer(ref, recorded.supplier_id)
    plant = sourcing.plant(recorded.supplier_id, recorded.plant_id)
    multiplier = offer.price_multiplier if offer else None
    coefficient = plant.price_coefficient if plant else None
    reproduced = (
        multiplier is not None
        and coefficient is not None
        and to_scale(reference * multiplier * coefficient) == unit_cost
    )
    return CatalogueBreakdown(
        reference_price=reference,
        supplier_id=recorded.supplier_id,
        supplier_name=(offer.name if offer and offer.name else recorded.supplier_id),
        supplier_multiplier=multiplier,
        plant_id=recorded.plant_id,
        origin_country=plant.origin_country if plant else None,
        plant_coefficient=coefficient,
        unit_cost=unit_cost,
        reproduced=reproduced,
    )


def _assembly(
    calculation: Calculation,
    bom: Bom,
    ref: str,
    path: str,
    scenario: Scenario,
    unchanged: bool,
) -> AssemblyBreakdown:
    lines = {line.part_ref: line for line in calculation.lines}
    children = []
    for child_ref, quantity in bom.children_of(ref):
        cost = lines[child_ref].full_unit_cost
        children.append(
            ChildCost(
                part_ref=child_ref,
                quantity=quantity,
                unit_cost=cost,
                contribution=None if cost is None else quantity * cost,
            )
        )
    contributions = [child.contribution for child in children]
    children_cost = (
        None if None in contributions else sum(contributions, Decimal(0))
    )
    # Le temps appliqué peut venir du scénario, en portée pièce ou chemin ; s'il
    # a changé depuis, on ne sait plus lequel a servi, et celui de la
    # nomenclature mentirait.
    parameter = scenario.parameter_for(ref, path) if unchanged else None
    if parameter is not None and parameter.labour_minutes is not None:
        labour_minutes = parameter.labour_minutes
    elif unchanged:
        labour_minutes = bom.parts[ref].labour_minutes
    else:
        labour_minutes = None
    return AssemblyBreakdown(
        children=tuple(children),
        children_cost=children_cost,
        labour_minutes=labour_minutes,
        labour_rate=scenario.labour_rate,
        labour_cost=lines[ref].own_unit_cost,
        unit_cost=lines[ref].full_unit_cost,
    )

