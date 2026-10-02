"""Lecture et validation des deux fichiers au démarrage uniquement."""
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from ..domain.dynamic_pricing import Component
from ..domain.price_drivers import classify_drivers

INDEX_NAMES = frozenset(('cuivre', 'aluminium', 'acier', 'lithium', 'nickel',
                         'energie', 'transport', 'semi_conducteurs', 'GBP_EUR'))
HISTORY_PATH = Path(__file__).with_name('data') / 'price_indices.json'


def _positive(value) -> Decimal:
    if isinstance(value, bool):
        raise ValueError('un booléen ne constitue pas une valeur numérique')
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError('valeur strictement positive et finie requise')
    return number


def _rows(node):
    if isinstance(node, list):
        for row in node:
            if not isinstance(row, dict) or 'id' not in row:
                raise ValueError('ligne de nomenclature sans identifiant')
            yield row
    elif isinstance(node, dict):
        for child in node.values():
            yield from _rows(child)
    else:
        raise ValueError('catégorie de nomenclature invalide')


def load_components(path: Path, classify: Callable[[str, str, str], Mapping[str, Decimal]] = classify_drivers
                    ) -> tuple[Component, ...]:
    with path.open(encoding='utf-8') as source:
        data = json.load(source, parse_float=Decimal)
    parts = []
    seen = set()
    try:
        rows = _rows(data['categories'])
        for row in rows:
            identifier = row.get('id')
            try:
                if not isinstance(identifier, str) or not identifier or identifier in seen:
                    raise ValueError('identifiant vide ou dupliqué')
                name = row['nom']
                if not isinstance(name, str) or not name.strip():
                    raise ValueError('nom requis')
                warranty = row['garantie']
                if not isinstance(warranty, bool):
                    raise ValueError('garantie doit être un booléen')
                price = _positive(row['prix_unitaire']['prix_eur'])
                quantity = _positive(row['quantite'])
                currency = row['fournisseur']['devise']
                if currency not in ('GBP', 'EUR'):
                    raise ValueError('devise sans indice de change disponible')
                drivers = dict(classify(name, row.get('description', ''), currency))
                if (not drivers or not drivers.keys() <= INDEX_NAMES
                        or any(not w.is_finite() or w < 0 for w in drivers.values())
                        or sum(drivers.values()) != 1):
                    raise ValueError('coefficients invalides : somme attendue 1')
                parts.append(Component(identifier, name, price, quantity, warranty,
                                       MappingProxyType(drivers)))
                seen.add(identifier)
            except (KeyError, TypeError, InvalidOperation, ValueError) as error:
                raise ValueError(f'Composant {identifier!r} invalide : {error}') from error
    except KeyError as error:
        raise ValueError('nomenclature sans catégories') from error
    if not parts:
        raise ValueError('nomenclature vide')
    return tuple(parts)


def load_history(path: Path = HISTORY_PATH):
    with path.open(encoding='utf-8') as source:
        data = json.load(source, parse_float=Decimal)
    try:
        raw = data['indices']
        if raw.keys() != INDEX_NAMES:
            raise ValueError('les neuf indices sont requis')
        history = {}
        for name, values in raw.items():
            if not isinstance(values, list) or len(values) != 365:
                raise ValueError(f'{name} : 365 valeurs requises')
            history[name] = tuple(_positive(value) for value in values)
        start = date.fromisoformat(data['start_date'])
        if (date(start.year + 1, 1, 1) - date(start.year, 1, 1)).days != 365:
            raise ValueError('une année non bissextile est requise')
        return MappingProxyType(history), start
    except (KeyError, TypeError, AttributeError, InvalidOperation) as error:
        raise ValueError(f'historique invalide : {error}') from error
