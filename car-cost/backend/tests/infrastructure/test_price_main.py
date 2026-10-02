"""Contrat du vrai point d'entrée Uvicorn, avec et sans configuration exportée."""
import importlib
import json
import sys

from fastapi.testclient import TestClient
import pytest

EXPECTED_PATHS = {
    '/api/prices', '/api/prices/{component_id}', '/api/vehicle-cost',
    '/api/production-cost', '/api/indices',
}


@pytest.fixture
def main_app(tmp_path, monkeypatch):
    path = tmp_path / 'bom.json'
    path.write_text(json.dumps({'categories': {'configuration': [{
        'id': 'BOM-0003', 'nom': 'ECU', 'description': 'Calculateur',
        'quantite': 1, 'garantie': False, 'fournisseur': {'devise': 'GBP'},
        'prix_unitaire': {'prix_eur': 100, 'devise': 'GBP'},
    }]}}))
    def load(configured):
        if configured:
            monkeypatch.setenv('CARCOST_PRICE_BOM', str(path))
        else:
            monkeypatch.delenv('CARCOST_PRICE_BOM', raising=False)
        # Uvicorn importe ce module dans un processus neuf : ne pas réutiliser
        # une instance créée par un autre test avec un environnement différent.
        monkeypatch.delitem(sys.modules, 'carcost.infrastructure.api.main', raising=False)
        return importlib.import_module('carcost.infrastructure.api.main').app
    yield load
    monkeypatch.delitem(sys.modules, 'carcost.infrastructure.api.main', raising=False)


def test_main_exposes_exact_pricing_paths_and_serves_all_routes(main_app):
    app = main_app(True)
    # OpenAPI expose les chemins effectifs même si FastAPI conserve
    # les routeurs inclus sous forme imbriquée dans app.routes.
    paths = app.openapi()['paths']
    assert {p for p in paths if p.startswith('/api/') and not p.startswith('/api/v1/')} == EXPECTED_PATHS
    assert all('get' in paths[p] for p in EXPECTED_PATHS)
    assert not any(path.startswith('/api/api/') for path in paths)
    with TestClient(app) as client:
        for path in EXPECTED_PATHS:
            response = client.get(path.replace('{component_id}', 'BOM-0003'),
                                  params={'vehicles': 100})
            assert response.status_code == 200, (path, response.text)
        assert client.get('/api/prices/inconnu').status_code == 404


def test_missing_environment_does_not_hide_pricing_routes(main_app):
    app = main_app(False)
    # OpenAPI expose les chemins effectifs même si FastAPI conserve
    # les routeurs inclus sous forme imbriquée dans app.routes.
    paths = app.openapi()['paths']
    assert {p for p in paths if p.startswith('/api/') and not p.startswith('/api/v1/')} == EXPECTED_PATHS
    assert all('get' in paths[p] for p in EXPECTED_PATHS)
    with TestClient(app) as client:
        for path in EXPECTED_PATHS:
            response = client.get(path.replace('{component_id}', 'BOM-0003'))
            assert response.status_code == 503
            assert 'CARCOST_PRICE_BOM' in response.text
