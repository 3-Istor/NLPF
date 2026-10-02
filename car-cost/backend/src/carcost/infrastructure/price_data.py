"""Chargement unique des trois BOM et des historiques au démarrage."""
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from types import MappingProxyType

from ..domain.dynamic_pricing import Component, PricingBom, component_rows
from ..domain.price_drivers import classify_drivers

INDEX_NAMES = frozenset(('cuivre', 'aluminium', 'acier', 'lithium', 'nickel',
                         'energie', 'transport', 'semi_conducteurs', 'GBP_EUR'))
HISTORY_PATH = Path(__file__).with_name('data') / 'price_indices.json'
DEFAULT_BOM_DIR = Path(__file__).with_name('data') / 'boms'
MODEL_FILES = MappingProxyType({
    'hybride': 'aston_martin_valhalla_hybride_phev.json',
    'thermique': 'aston_martin_valhalla_thermique.json',
    'electrique': 'aston_martin_valhalla_electrique.json',
})


def _number(value, *, allow_zero=False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError('nombre requis')
    number = Decimal(str(value))
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
        raise ValueError('valeur positive et finie requise')
    return number


def _positive(value) -> Decimal:
    # L'historique versionné stocke ses décimaux sous forme de chaînes.
    return _number(Decimal(str(value)))


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _load_bom(path: Path) -> PricingBom:
    with path.open(encoding='utf-8') as source:
        data = json.load(source)
    parts = {}
    try:
        for row in component_rows(data['categories']):
            identifier = row.get('id')
            try:
                if not isinstance(identifier, str) or not identifier or identifier in parts:
                    raise ValueError('identifiant vide ou dupliqué')
                if not isinstance(row['nom'], str) or not row['nom'].strip():
                    raise ValueError('nom requis')
                if not isinstance(row['description'], str):
                    raise ValueError('description textuelle requise')
                if not isinstance(row['garantie'], bool):
                    raise ValueError('garantie doit être un booléen')
                quantity = _number(row['quantite'])
                stock = _number(row['quantite_sav'], allow_zero=True)
                total = _number(row['quantite_totale'])
                if total != quantity + stock:
                    raise ValueError('quantite_totale doit valoir quantite + quantite_sav')
                price = _number(row['prix_unitaire']['prix'])
                price_eur = _number(row['prix_unitaire']['prix_eur'])
                if row['prix_unitaire']['devise'] not in ('GBP', 'EUR'):
                    raise ValueError('devise de prix non prise en charge')
                if row['prix_final']['devise'] != row['prix_unitaire']['devise']:
                    raise ValueError('les devises unitaire et finale doivent coïncider')
                _number(row['prix_final']['prix'])
                _number(row['prix_final']['prix_eur'])
                drivers = classify_drivers(row['nom'], row['description'], row['fournisseur']['devise'])
                if (not drivers or not drivers.keys() <= INDEX_NAMES
                        or any(not w.is_finite() or w < 0 for w in drivers.values())
                        or sum(drivers.values()) != 1):
                    raise ValueError('coefficients invalides : somme attendue 1')
                parts[identifier] = Component(identifier, price, price_eur, total,
                                              MappingProxyType(drivers))
            except (KeyError, TypeError, InvalidOperation, ValueError) as error:
                raise ValueError(f'{path.name} : composant {identifier!r} invalide : {error}') from error
    except (KeyError, TypeError) as error:
        raise ValueError(f'{path.name} : nomenclature sans catégories valides') from error
    if not parts:
        raise ValueError(f'{path.name} : nomenclature vide')
    return PricingBom(_freeze(data), MappingProxyType(parts))


def load_boms(directory: Path = DEFAULT_BOM_DIR):
    return MappingProxyType({model: _load_bom(directory / filename)
                             for model, filename in MODEL_FILES.items()})


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
