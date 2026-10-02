"""Valorisation d'une nomenclature plate et stock SAV, sans effet de bord."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Mapping

SAV_RATE = Decimal('0.03')


@dataclass(frozen=True)
class Component:
    id: str
    name: str
    base_price: Decimal
    quantity: Decimal
    warranty: bool
    drivers_prix: Mapping[str, Decimal]


def current_price(component: Component, variations: Mapping[str, Decimal]) -> Decimal:
    factor = 1 + sum(weight * variations[name]
                     for name, weight in component.drivers_prix.items())
    return component.base_price * factor


def production_quantities(component: Component, vehicles: int) -> tuple[Decimal, Decimal]:
    production = component.quantity * vehicles
    purchase = ((production * (1 + SAV_RATE)).to_integral_value(rounding=ROUND_CEILING)
                if component.warranty else production)
    return production, purchase
