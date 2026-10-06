"""Du prix de référence au prix unitaire d'une pièce achetée.

    prix unitaire = référence × multiplicateur fournisseur × coefficient d'usine

Les trois facteurs sont conservés séparément jusqu'à l'explication : sans eux,
« que me coûte cette usine ? » n'a pas de réponse (ADR-0010).

Un ensemble fabriqué ne passe jamais par ici : il n'a pas de prix, et lui en
chercher un serait exactement la double comptabilisation que l'ADR-0008 rend
impossible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from ..domain.bom import Bom
from ..domain.prices import PriceSnapshot
from .scenario import Scenario, ScenarioParameter, Sourcing


#: Les prix sont stockés à l'échelle 6 (NUMERIC(18,6)). Le produit de trois
#: facteurs à 6 décimales en porterait 18, dont douze que la donnée ne contient
#: pas. On ramène donc le prix unitaire à l'échelle réelle, une fois, ici — et
#: plus jamais ensuite : c'est la seule façon pour que les contributions se
#: somment exactement au total (ADR-0011).
SCALE = Decimal("0.000001")


def to_scale(value: Decimal) -> Decimal:
    return value.quantize(SCALE, rounding=ROUND_HALF_UP)


class ParameterNotApplicable(Exception):
    """Un paramètre posé sur une pièce qui ne peut pas le porter."""


class PlantNotAvailableForSupplier(Exception):
    """L'usine demandée n'appartient pas au fournisseur retenu."""


class PriceOverrideNeedsJustification(Exception):
    """Un prix forcé sans justification n'entre pas."""


class NoSupplierForPart(Exception):
    """Une pièce achetée sans aucun fournisseur déclaré."""


@dataclass(frozen=True)
class PriceExplanation:
    """De quoi reconstituer le prix à l'écran, facteur par facteur."""

    part_ref: str
    unit_price: Decimal
    reference_price: Decimal | None = None
    supplier_id: str | None = None
    supplier_multiplier: Decimal | None = None
    plant_id: str | None = None
    plant_coefficient: Decimal | None = None
    origin_country: str | None = None
    override_justification: str | None = None
    #: kg CO2e/kg transporté par l'usine retenue. `None` sur un prix forcé :
    #: aucune usine n'est retenue, donc aucun transport à annoncer.
    transport_co2_per_kg: Decimal | None = None

    @property
    def is_overridden(self) -> bool:
        return self.override_justification is not None


@dataclass(frozen=True)
class ResolvedPrices:
    prices: dict[str, Decimal]
    explanations: dict[str, PriceExplanation]
    #: Pièces achetées dont aucun prix n'est connu. Jamais remplacées par zéro.
    missing: tuple[str, ...]
    path_prices: dict[str, Decimal] = field(default_factory=dict)
    path_explanations: dict[str, PriceExplanation] = field(default_factory=dict)
    transport_co2_per_kg: dict[str, Decimal] = field(default_factory=dict)
    path_transport_co2_per_kg: dict[str, Decimal | None] = field(default_factory=dict)


def resolve_unit_prices(
    bom: Bom, sourcing: Sourcing, snapshot: PriceSnapshot, scenario: Scenario
) -> ResolvedPrices:
    validate_parameters(bom, scenario)

    prices: dict[str, Decimal] = {}
    explanations: dict[str, PriceExplanation] = {}
    missing: list[str] = []

    for ref, part in bom.parts.items():
        if not part.is_purchased:
            continue

        resolved = resolve_purchase_price(
            sourcing, snapshot, ref, scenario.parameter_for(ref)
        )
        if resolved is None:
            missing.append(ref)
        else:
            prices[ref] = resolved.unit_price
            explanations[ref] = resolved

    path_prices: dict[str, Decimal] = {}
    path_explanations: dict[str, PriceExplanation] = {}
    for parameter in scenario.parameters:
        if (
            parameter.scope != "path"
            or not bom.parts[parameter.part_ref].is_purchased
        ):
            continue
        resolved = resolve_purchase_price(
            sourcing,
            snapshot,
            parameter.part_ref,
            scenario.parameter_for(parameter.part_ref, parameter.path),
        )
        if resolved is not None:
            path_prices[parameter.path] = resolved.unit_price
            path_explanations[parameter.path] = resolved

    # Un prix forcé n'a pas d'usine : la pièce reste hors du dictionnaire et le
    # moteur la lit comme « transport inconnu ». Sur un chemin, l'absence ne
    # suffirait pas — elle voudrait dire « même usine que la pièce » — d'où le
    # `None` explicite.
    transport_co2_per_kg = {
        ref: explanation.transport_co2_per_kg
        for ref, explanation in explanations.items()
        if explanation.transport_co2_per_kg is not None
    }
    path_transport_co2_per_kg = {
        path: explanation.transport_co2_per_kg
        for path, explanation in path_explanations.items()
    }

    return ResolvedPrices(
        prices=prices,
        explanations=explanations,
        missing=tuple(sorted(missing)),
        path_prices=path_prices,
        path_explanations=path_explanations,
        transport_co2_per_kg=transport_co2_per_kg,
        path_transport_co2_per_kg=path_transport_co2_per_kg,
    )


def resolve_purchase_price(
    sourcing: Sourcing,
    snapshot: PriceSnapshot,
    part_ref: str,
    parameter: ScenarioParameter | None,
) -> PriceExplanation | None:
    """Résout une option de sourcing sans traverser le graphe."""
    if parameter is not None and parameter.price_override is not None:
        return PriceExplanation(
            part_ref=part_ref,
            unit_price=to_scale(parameter.price_override),
            override_justification=parameter.price_override_justification,
        )
    reference = snapshot.prices.get(part_ref)
    if reference is None:
        return None
    offer, plant = _sourcing_for(sourcing, part_ref, parameter)
    unit_price = to_scale(
        reference * offer.price_multiplier * plant.price_coefficient
    )
    return PriceExplanation(
        part_ref=part_ref,
        unit_price=unit_price,
        reference_price=reference,
        supplier_id=offer.supplier_id,
        supplier_multiplier=offer.price_multiplier,
        plant_id=plant.plant_id,
        plant_coefficient=plant.price_coefficient,
        origin_country=plant.origin_country,
        transport_co2_per_kg=plant.transport_co2_kg_per_kg,
    )


def validate_parameters(bom: Bom, scenario: Scenario) -> None:
    """Refuser tôt, et nommer la pièce fautive.

    La base porte les mêmes interdits par clés étrangères composites ; les
    répéter ici n'est pas une redondance inutile : c'est ce qui permet de
    répondre 422 avec un message utile au lieu d'une erreur de contrainte.
    """
    for parameter in scenario.parameters:
        part = bom.parts.get(parameter.part_ref)
        if part is None:
            raise ParameterNotApplicable(
                f"{parameter.part_ref} n'existe pas dans cette nomenclature"
            )
        if part.is_purchased and (
            parameter.labour_minutes is not None or parameter.labour_rate is not None
        ):
            raise ParameterNotApplicable(
                f"{part.ref} est une pièce achetée : elle n'a pas de main-d'œuvre"
            )
        if not part.is_purchased and parameter.touches_purchase:
            raise ParameterNotApplicable(
                f"{part.ref} est un ensemble fabriqué : ni fournisseur, ni usine, "
                f"ni devise d'achat, ni prix propre"
            )
        if parameter.price_override is not None and not (
            parameter.price_override_justification or ""
        ).strip():
            raise PriceOverrideNeedsJustification(
                f"{part.ref} : un prix forcé se justifie"
            )


def _sourcing_for(
    sourcing: Sourcing, part_ref: str, parameter: ScenarioParameter | None
):
    supplier_id = parameter.supplier_id if parameter else None
    offer = (
        sourcing.offer(part_ref, supplier_id)
        if supplier_id
        else sourcing.default_offer(part_ref)
    )
    if offer is None:
        raise NoSupplierForPart(
            f"{part_ref} : aucun fournisseur "
            + (f"« {supplier_id} »" if supplier_id else "déclaré")
        )

    plant_id = parameter.plant_id if parameter else None
    if plant_id is None:
        plant = sourcing.default_plant(offer.supplier_id)
    else:
        plant = sourcing.plant(offer.supplier_id, plant_id)
        if plant is None:
            raise PlantNotAvailableForSupplier(
                f"l'usine {plant_id} n'appartient pas au fournisseur "
                f"{offer.supplier_id}"
            )
    if plant is None:
        raise NoSupplierForPart(
            f"{offer.supplier_id} n'a aucun site de production déclaré"
        )
    return offer, plant
