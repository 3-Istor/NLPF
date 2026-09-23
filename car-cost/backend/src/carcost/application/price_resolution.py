"""Du prix de référence au prix unitaire d'une pièce achetée.

    prix unitaire = référence × multiplicateur fournisseur × coefficient d'usine

Les trois facteurs sont conservés séparément jusqu'à l'explication : sans eux,
« que me coûte cette usine ? » n'a pas de réponse (ADR-0010).

Un ensemble fabriqué ne passe jamais par ici : il n'a pas de prix, et lui en
chercher un serait exactement la double comptabilisation que l'ADR-0008 rend
impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..domain.bom import Bom
from ..domain.prices import PriceSnapshot
from .scenario import Scenario, ScenarioParameter, Sourcing


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

    @property
    def is_overridden(self) -> bool:
        return self.override_justification is not None


@dataclass(frozen=True)
class ResolvedPrices:
    prices: dict[str, Decimal]
    explanations: dict[str, PriceExplanation]
    #: Pièces achetées dont aucun prix n'est connu. Jamais remplacées par zéro.
    missing: tuple[str, ...]


def resolve_unit_prices(
    bom: Bom, sourcing: Sourcing, snapshot: PriceSnapshot, scenario: Scenario
) -> ResolvedPrices:
    _reject_inapplicable_parameters(bom, scenario)

    prices: dict[str, Decimal] = {}
    explanations: dict[str, PriceExplanation] = {}
    missing: list[str] = []

    for ref, part in bom.parts.items():
        if not part.is_purchased:
            continue

        parameter = scenario.parameter_for(ref)

        if parameter is not None and parameter.price_override is not None:
            explanations[ref] = PriceExplanation(
                part_ref=ref,
                unit_price=parameter.price_override,
                override_justification=parameter.price_override_justification,
            )
            prices[ref] = parameter.price_override
            continue

        reference = snapshot.prices.get(ref)
        if reference is None:
            missing.append(ref)
            continue

        offer, plant = _sourcing_for(sourcing, ref, parameter)
        unit_price = reference * offer.price_multiplier * plant.price_coefficient
        prices[ref] = unit_price
        explanations[ref] = PriceExplanation(
            part_ref=ref,
            unit_price=unit_price,
            reference_price=reference,
            supplier_id=offer.supplier_id,
            supplier_multiplier=offer.price_multiplier,
            plant_id=plant.plant_id,
            plant_coefficient=plant.price_coefficient,
            origin_country=plant.origin_country,
        )

    return ResolvedPrices(
        prices=prices, explanations=explanations, missing=tuple(sorted(missing))
    )


def _reject_inapplicable_parameters(bom: Bom, scenario: Scenario) -> None:
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
        if part.is_purchased and parameter.labour_minutes is not None:
            raise ParameterNotApplicable(
                f"{part.ref} est une pièce achetée : elle n'a pas de main-d'œuvre"
            )
        if not part.is_purchased and parameter.touches_purchase:
            raise ParameterNotApplicable(
                f"{part.ref} est un ensemble fabriqué : ni fournisseur, ni usine, "
                f"ni prix propre"
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
