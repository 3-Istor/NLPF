"""Un seul endpoint renvoie le document complet, sans arrondi métier ni SAV ajouté."""
from copy import deepcopy
from decimal import Decimal as D

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from carcost.application.price_simulation import PriceSimulation
from carcost.domain.dynamic_pricing import component_rows
from carcost.infrastructure.api.price_routes import router
from carcost.infrastructure.price_data import load_boms, load_history
from infrastructure.test_price_data import write_models, first_row


@pytest.fixture
def pricing_client(tmp_path):
    originals = write_models(tmp_path)
    models = load_boms(tmp_path)
    history, start_date = load_history()
    now = [0.0]
    service = PriceSimulation(models, history, start_date=start_date, clock=lambda: now[0])
    app = FastAPI()
    app.state.price_simulation = service
    app.include_router(router)
    with TestClient(app) as client:
        yield client, originals, now, service


def without_money(document):
    document = deepcopy(document)
    for row in component_rows(document['categories']):
        for field in ('prix_unitaire', 'prix_final'):
            row[field].pop('prix')
            row[field].pop('prix_eur')
    return document


@pytest.mark.parametrize('model', ['hybride', 'thermique', 'electrique'])
def test_selected_document_keeps_all_non_price_fields(pricing_client, model):
    client, originals, now, _ = pricing_client
    now[0] = 1200
    response = client.get('/api/prices', params={'model': model})
    assert response.status_code == 200
    data = response.json()
    assert without_money(data) == without_money(originals[model])
    row = first_row(data)
    assert row['id'] == f'{model}-01'
    assert (row['quantite'], row['quantite_sav'], row['quantite_totale']) == (4, 1, 5)
    for field in ('prix_unitaire', 'prix_final'):
        for currency in ('prix', 'prix_eur'):
            value = row[field][currency]
            assert type(value) in (float, int)
            assert D(str(value)) == D(str(value)).quantize(D('.01'))


def test_supplied_stock_used_even_when_warranty_false(pricing_client):
    client, _, _, _ = pricing_client
    for model in ('hybride', 'thermique'):
        row = first_row(client.get('/api/prices', params={'model': model}).json())
        assert row['prix_unitaire']['prix'] == 100
        assert row['prix_unitaire']['prix_eur'] == 120
        assert row['prix_final']['prix'] == 100 * 5
        assert row['prix_final']['prix_eur'] == 120 * 5


def test_polling_and_model_switch_do_not_mutate_or_compound(pricing_client):
    client, _, now, service = pricing_client
    first = client.get('/api/prices?model=hybride').json()
    now[0] = 5
    later = client.get('/api/prices?model=hybride').json()
    assert first_row(first)['prix_unitaire'] != first_row(later)['prix_unitaire']
    assert without_money(first) == without_money(later)
    assert first_row(client.get('/api/prices?model=electrique').json())['id'] == 'electrique-01'
    assert client.get('/api/prices?model=hybride').json() == later
    assert first_row(service.models['hybride'].document)['prix_unitaire']['prix'] == 100
    now[0] = 0
    assert client.get('/api/prices?model=hybride').json() == first


@pytest.mark.parametrize('model', ['essence', 'hybrid', 'electric', 'thermal', 'inconnu', 'Hybride', ''])
def test_unknown_models_return_400(pricing_client, model):
    client, _, _, _ = pricing_client
    response = client.get('/api/prices', params={'model': model})
    assert response.status_code == 400
    assert response.json() == {'detail': 'Unknown model. Allowed values: hybride, thermique, electrique'}


def test_model_is_required(pricing_client):
    assert pricing_client[0].get('/api/prices').status_code == 422


def test_removed_routes_are_not_exposed(pricing_client):
    client = pricing_client[0]
    assert set(client.get('/openapi.json').json()['paths']) == {'/api/prices'}
    for path in ('/api/prices/hybride-01', '/api/vehicle-cost', '/api/production-cost', '/api/indices'):
        assert client.get(path).status_code == 404


def test_final_prices_are_computed_before_response_rounding(pricing_client):
    client, _, now, service = pricing_client
    # Une variation choisie donne 100,006 : le total interne vaut 500,030,
    # et non 500,050 obtenu en multipliant un prix unitaire déjà arrondi.
    service.history = {name: (D('100'),) + (D('100.006'),) * 364
                       for name in service.history}
    now[0] = 1200
    row = first_row(client.get('/api/prices?model=hybride').json())
    assert row['prix_unitaire']['prix'] == 100.01
    assert row['prix_final']['prix'] == 500.03
    raw = first_row(service.quote('hybride'))
    assert D(str(row['prix_final']['prix'])) == raw['prix_final']['prix'].quantize(D('.01'))
    assert raw['prix_final']['prix'] == raw['prix_unitaire']['prix'] * D('5')
