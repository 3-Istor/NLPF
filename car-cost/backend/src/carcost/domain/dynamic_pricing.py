"""Valorisation depuis les bases immuables et la quantité totale fournie."""
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Component:
    id: str
    base_price: Decimal
    base_price_eur: Decimal
    total_quantity: Decimal
    drivers_prix: Mapping[str, Decimal]


@dataclass(frozen=True)
class PricingBom:
    document: Mapping
    components: Mapping[str, Component]


@dataclass(frozen=True)
class ComponentPrices:
    unit_price: Decimal
    unit_price_eur: Decimal
    final_price: Decimal
    final_price_eur: Decimal


def current_prices(component: Component, variations: Mapping[str, Decimal]) -> ComponentPrices:
    factor = 1 + sum(weight * variations[name]
                     for name, weight in component.drivers_prix.items())
    price = component.base_price * factor
    price_eur = component.base_price_eur * factor
    return ComponentPrices(price, price_eur, price * component.total_quantity,
                           price_eur * component.total_quantity)


def component_rows(categories):
    """Les catégories regroupent les lignes ; elles ne portent pas de quantités."""
    if isinstance(categories, Mapping):
        for child in categories.values():
            yield from component_rows(child)
    elif isinstance(categories, (list, tuple)):
        for row in categories:
            if not isinstance(row, Mapping) or 'id' not in row:
                raise ValueError('ligne de nomenclature sans identifiant')
            yield row
    else:
        raise ValueError('catégorie de nomenclature invalide')
