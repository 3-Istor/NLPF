"""Le scénario : ce que l'utilisateur règle, et le catalogue de sourcing.

Un paramètre porte toujours sa **portée**, explicite et jamais déduite : soit il
vaut pour toutes les occurrences de la pièce, soit pour une occurrence désignée
par son chemin (ADR-0002). L'interface doit pouvoir dire laquelle, donc le
modèle doit la porter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Mapping, Sequence

Scope = Literal["part", "path"]


@dataclass(frozen=True)
class SupplierOffer:
    supplier_id: str
    price_multiplier: Decimal
    is_default: bool


@dataclass(frozen=True)
class Plant:
    plant_id: str
    supplier_id: str
    origin_country: str
    price_coefficient: Decimal
    transport_co2_kg_per_kg: Decimal
    is_default: bool


@dataclass(frozen=True)
class Sourcing:
    """Qui peut fournir quoi, et depuis où."""

    offers: Mapping[str, Sequence[SupplierOffer]]
    plants: Mapping[str, Sequence[Plant]]

    def offers_for(self, part_ref: str) -> Sequence[SupplierOffer]:
        return self.offers.get(part_ref, ())

    def default_offer(self, part_ref: str) -> SupplierOffer | None:
        candidates = self.offers_for(part_ref)
        for offer in candidates:
            if offer.is_default:
                return offer
        return candidates[0] if candidates else None

    def offer(self, part_ref: str, supplier_id: str) -> SupplierOffer | None:
        for candidate in self.offers_for(part_ref):
            if candidate.supplier_id == supplier_id:
                return candidate
        return None

    def default_plant(self, supplier_id: str) -> Plant | None:
        candidates = self.plants.get(supplier_id, ())
        for plant in candidates:
            if plant.is_default:
                return plant
        return candidates[0] if candidates else None

    def plant(self, supplier_id: str, plant_id: str) -> Plant | None:
        for candidate in self.plants.get(supplier_id, ()):
            if candidate.plant_id == plant_id:
                return candidate
        return None


@dataclass(frozen=True)
class ScenarioParameter:
    part_ref: str
    scope: Scope
    path: str | None = None
    supplier_id: str | None = None
    plant_id: str | None = None
    price_override: Decimal | None = None
    price_override_justification: str | None = None
    labour_minutes: Decimal | None = None

    @property
    def touches_purchase(self) -> bool:
        return any(
            value is not None
            for value in (self.supplier_id, self.plant_id, self.price_override)
        )


@dataclass(frozen=True)
class Scenario:
    id: str
    bom_version: str
    display_currency: str
    labour_rate: Decimal
    active_rules: frozenset[str] = field(
        default_factory=lambda: frozenset({"labour"})
    )
    parameters: Sequence[ScenarioParameter] = ()

    def parameter_for(self, part_ref: str) -> ScenarioParameter | None:
        """Le paramètre applicable à une pièce, portée pièce.

        La portée chemin n'est pas encore résolue par le moteur : le champ
        existe, il est persisté, et la tranche T2 le fera jouer. En attendant,
        un paramètre de portée chemin est ignoré plutôt que traité comme un
        paramètre de portée pièce — l'appliquer partout serait pire que de ne
        pas l'appliquer.
        """
        for parameter in self.parameters:
            if parameter.part_ref == part_ref and parameter.scope == "part":
                return parameter
        return None
