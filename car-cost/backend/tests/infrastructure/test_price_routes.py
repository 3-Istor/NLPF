"""Les routes ne doivent consulter ni disque ni réseau après leur démarrage."""
import builtins
from decimal import Decimal as D
from pathlib import Path
import socket

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from carcost.application.price_simulation import PriceSimulation
from carcost.domain.dynamic_pricing import Component
from carcost.infrastructure.api.price_routes import router


def test_all_routes_without_disk_or_network(monkeypatch):
    now = [0.0]
    service = PriceSimulation([
        Component('A', 'Câble', D('10.25'), D('2.5'), True, {'cuivre': D('1')}),
        Component('B', 'Vis', D('3'), D('4'), False, {'cuivre': D('1')}),
    ], {'cuivre': tuple(D(100 + i) for i in range(365))}, clock=lambda: now[0])
    app = FastAPI()
    app.state.price_simulation = service
    app.include_router(router)
    with TestClient(app) as client:
        def forbidden(*args, **kwargs):
            raise AssertionError('accès disque ou réseau pendant un GET')
        with monkeypatch.context() as guard:
            guard.setattr(builtins, 'open', forbidden)
            guard.setattr(Path, 'open', forbidden)
            guard.setattr(socket.socket, 'connect', forbidden)
            guard.setattr(socket, 'getaddrinfo', forbidden)
            prices = client.get('/api/prices').json()
            assert len(prices) == 2
            part = client.get('/api/prices/A').json()
            assert part == prices[0]
            assert D(part['cout_par_voiture_eur']) == D(part['prix_unitaire_actuel_eur']) * D(part['quantite'])
            assert D(part['variation_pct']) == 0
            vehicle = client.get('/api/vehicle-cost').json()
            assert D(vehicle['cout_bom_eur']) == D('37.625')
            production = client.get('/api/production-cost?vehicles=100').json()
            assert D(production['cout_production_eur']) == D('3762.5')
            assert D(production['cout_stock_sav_eur']) == D('82')
            assert D(production['cout_total_eur']) == D('3844.5')
            assert D(client.get('/api/indices').json()['indices']['cuivre']) == 100
            missing = client.get('/api/prices/inconnu')
            assert missing.status_code == 404
            assert missing.json()['error']['code'] == 'COMPONENT_NOT_FOUND'
            for value in ('-1', '1.5', 'abc'):
                assert client.get(f'/api/production-cost?vehicles={value}').status_code == 422
            assert D(client.get('/api/production-cost?vehicles=0').json()['cout_total_eur']) == 0
            now[0] += 100
            assert client.get('/api/prices/A').json()['prix_unitaire_actuel_eur'] != part['prix_unitaire_actuel_eur']
