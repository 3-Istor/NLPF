"""Chargement unique, catégories imbriquées et rejet des données ambiguës."""
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from carcost.infrastructure.price_data import load_components, load_history


def write_bom(tmp_path, rows):
    path = tmp_path / 'bom.json'
    path.write_text(json.dumps({'categories': {'motorisation': {'batteries': rows}}}))
    return path


def row(**changes):
    return dict(id='BOM-42', nom='Pièce', description='Test', quantite=2.5,
                prix_unitaire={'prix_eur': 10.25, 'devise': 'GBP'}, garantie=True,
                fournisseur={'devise': 'GBP'},
                **changes)


def test_nested_categories_preserve_ids_and_decimals(tmp_path):
    path = write_bom(tmp_path, [row()])
    original = path.read_bytes()
    part, = load_components(path, lambda *_: {'energie': D('1')})
    assert (part.id, part.base_price, part.quantity, part.warranty) == (
        'BOM-42', D('10.25'), D('2.5'), True)
    assert path.read_bytes() == original


@pytest.mark.parametrize('field,value', [('garantie', 'false'), ('quantite', -1),
                                       ('quantite', float('nan')), ('id', '')])
def test_invalid_component_is_rejected(tmp_path, field, value):
    data = row()
    data[field] = value
    with pytest.raises(ValueError):
        load_components(write_bom(tmp_path, [data]), lambda *_: {'energie': D('1')})


def test_duplicate_id_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='BOM-42'):
        load_components(write_bom(tmp_path, [row(), row()]), lambda *_: {'energie': D('1')})


def test_missing_price_is_not_zero(tmp_path):
    data = row()
    data['prix_unitaire'].pop('prix_eur')
    with pytest.raises(ValueError, match='BOM-42'):
        load_components(write_bom(tmp_path, [data]), lambda *_: {'energie': D('1')})


def test_history_has_365_positive_values_for_each_index():
    history, start = load_history()
    assert len(history) == 9
    assert start.isoformat() == '2026-01-01'
    assert all(len(values) == 365 and all(v > 0 for v in values)
               for values in history.values())


def test_incomplete_history_is_rejected(tmp_path):
    path = tmp_path / 'indices.json'
    path.write_text(json.dumps({'start_date': '2026-01-01', 'indices': {}}))
    with pytest.raises(ValueError):
        load_history(path)


def test_supplier_currency_controls_fx(tmp_path):
    data = row()
    data['fournisseur']['devise'] = 'EUR'
    part, = load_components(write_bom(tmp_path, [data]))
    assert part.drivers_prix['GBP_EUR'] == 0
    assert sum(part.drivers_prix.values()) == 1


def test_missing_supplier_currency_is_rejected(tmp_path):
    data = row()
    data.pop('fournisseur')
    with pytest.raises(ValueError, match='BOM-42'):
        load_components(write_bom(tmp_path, [data]))
