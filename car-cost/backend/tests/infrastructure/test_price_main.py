"""Le vrai point d'entrée Uvicorn expose un seul endpoint pricing."""
import importlib
import sys

from fastapi.testclient import TestClient
import pytest

from infrastructure.test_price_data import write_models


@pytest.fixture
def main_app(tmp_path, monkeypatch):
    write_models(tmp_path)
    def load(packaged=False):
        if packaged:
            monkeypatch.delenv('CARCOST_PRICE_BOM_DIR', raising=False)
        else:
            monkeypatch.setenv('CARCOST_PRICE_BOM_DIR', str(tmp_path))
        monkeypatch.delitem(sys.modules, 'carcost.infrastructure.api.main', raising=False)
        return importlib.import_module('carcost.infrastructure.api.main').app
    yield load
    monkeypatch.delitem(sys.modules, 'carcost.infrastructure.api.main', raising=False)


@pytest.mark.parametrize('packaged', [False, True])
def test_main_serves_three_models_with_only_one_pricing_route(main_app, packaged):
    app = main_app(packaged)
    paths = app.openapi()['paths']
    assert {p for p in paths if p.startswith('/api/') and not p.startswith('/api/v1/')} == {'/api/prices'}
    assert '/api/v1/bom/versions' in paths
    assert '/api/v1/scenarios' in paths
    parameter, = paths['/api/prices']['get']['parameters']
    assert parameter['name'] == 'model'
    assert parameter['required']
    with TestClient(app) as client:
        for model in ('hybride', 'thermique', 'electrique'):
            response = client.get('/api/prices', params={'model': model})
            assert response.status_code == 200
            assert 'categories' in response.json()
        assert client.get('/api/prices?model=essence').status_code == 400
        assert client.get('/api/prices').status_code == 422
        assert client.get('/health').status_code == 200
        for route in ('/api/prices/BOM-0003', '/api/vehicle-cost', '/api/production-cost', '/api/indices'):
            assert client.get(route).status_code == 404
