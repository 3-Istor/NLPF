"""Les trois BOM sont validées et figées sans modifier leurs fichiers."""
import json
from decimal import Decimal as D

import pytest

from carcost.infrastructure.price_data import load_boms, load_history, DEFAULT_BOM_DIR, MODEL_FILES


def document(model='hybride', warranty=True):
    return {'vehicule': {'modele': 'Valhalla', 'configuration': model},
            'categories': {'motorisation': {'pieces': [{
                'id': f'{model}-01', 'nom': 'Faisceau', 'description': 'Cuivre',
                'quantite': 4.0, 'quantite_sav': 1, 'quantite_totale': 5.0,
                'unite': 'piece', 'fournisseur': {'nom': 'Fournisseur', 'devise': 'GBP'},
                'prix_unitaire': {'prix': 100.0, 'prix_eur': 120.0, 'devise': 'GBP'},
                'prix_final': {'prix': 500.0, 'prix_eur': 600.0, 'devise': 'GBP'},
                'garantie': warranty,
            }]}}}


def write_models(directory):
    directory.mkdir(parents=True, exist_ok=True)
    data = {}
    for name, filename in MODEL_FILES.items():
        data[name] = document(name, warranty=name != 'thermique')
        (directory / filename).write_text(json.dumps(data[name]), encoding='utf-8')
    return data


def first_row(data):
    return data['categories']['motorisation']['pieces'][0]


def test_three_models_are_loaded_and_frozen(tmp_path):
    originals = write_models(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    models = load_boms(tmp_path)
    assert set(models) == {'hybride', 'thermique', 'electrique'}
    for model, bom in models.items():
        part = bom.components[f'{model}-01']
        assert (part.base_price, part.base_price_eur, part.total_quantity) == (D('100'), D('120'), D('5'))
        assert first_row(bom.document)['id'] == first_row(originals[model])['id']
        with pytest.raises(TypeError):
            first_row(bom.document)['prix_unitaire']['prix'] = 99
        with pytest.raises(TypeError):
            bom.document['categories']['motorisation']['pieces'][0] = {}
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize('field,value', [('quantite', -1), ('quantite_sav', -1),
    ('quantite_sav', float('nan')), ('quantite_totale', 6), ('garantie', 'false'), ('id', '')])
def test_bad_component_is_rejected(tmp_path, field, value):
    data = write_models(tmp_path)['hybride']
    first_row(data)[field] = value
    (tmp_path / MODEL_FILES['hybride']).write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_boms(tmp_path)


def test_duplicate_id_is_rejected_within_a_model(tmp_path):
    data = write_models(tmp_path)['hybride']
    data['categories']['motorisation']['pieces'].append(first_row(data).copy())
    (tmp_path / MODEL_FILES['hybride']).write_text(json.dumps(data))
    with pytest.raises(ValueError, match='hybride-01'):
        load_boms(tmp_path)


def test_missing_file_prevents_partial_startup(tmp_path):
    write_models(tmp_path)
    (tmp_path / MODEL_FILES['electrique']).unlink()
    with pytest.raises(FileNotFoundError):
        load_boms(tmp_path)


def test_supplier_currency_controls_fx(tmp_path):
    data = write_models(tmp_path)['hybride']
    first_row(data)['fournisseur']['devise'] = 'EUR'
    (tmp_path / MODEL_FILES['hybride']).write_text(json.dumps(data))
    part = load_boms(tmp_path)['hybride'].components['hybride-01']
    assert part.drivers_prix['GBP_EUR'] == 0
    assert sum(part.drivers_prix.values()) == 1


def test_packaged_files_have_their_own_components_and_valid_coefficients():
    models = load_boms(DEFAULT_BOM_DIR)
    assert {m: len(b.components) for m, b in models.items()} == {
        'hybride': 635, 'thermique': 575, 'electrique': 514}
    assert 'BOM-0504' in models['thermique'].components
    assert 'BOM-0504' not in models['hybride'].components
    assert 'BOM-0601' in models['electrique'].components
    assert 'BOM-0601' not in models['thermique'].components
    assert all(sum(p.drivers_prix.values()) == 1 for b in models.values() for p in b.components.values())


def test_history_has_365_positive_values_for_each_index():
    history, start = load_history()
    assert len(history) == 9
    assert start.isoformat() == '2026-01-01'
    assert all(len(values) == 365 and all(v > 0 for v in values) for values in history.values())
