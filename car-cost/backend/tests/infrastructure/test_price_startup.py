"""L'application existante charge une fois les fichiers, puis ne fait que calculer."""
import builtins
import json
from decimal import Decimal
from pathlib import Path
import socket
from unittest.mock import Mock

from fastapi.testclient import TestClient

from carcost.infrastructure.api.app import Repositories, create_app
from carcost.infrastructure import price_data


def test_startup_loads_once_and_routes_use_only_memory(tmp_path, monkeypatch):
    path = tmp_path / 'bom.json'
    path.write_text(json.dumps({'categories': {'electricite': [{
        'id': 'ORIGINAL-42', 'nom': 'Faisceau HV', 'description': 'Cuivre',
        'quantite': 2.5, 'garantie': True, 'fournisseur': {'devise': 'EUR'},
        'prix_unitaire': {'prix_eur': 10.25, 'devise': 'EUR'},
    }]}}))
    original = path.read_bytes()
    reads = []
    original_open = Path.open
    def tracked_open(self, *args, **kwargs):
        reads.append(self)
        return original_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', tracked_open)
    now = [0.0]
    app = create_app(Repositories(bom=Mock()), price_bom_path=path,
                     price_clock=lambda: now[0])
    assert reads == []
    def forbidden(*args, **kwargs):
        raise AssertionError('accès disque ou réseau inattendu')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    with TestClient(app) as client:
        assert reads == [path, price_data.HISTORY_PATH]
        with monkeypatch.context() as guard:
            guard.setattr(Path, 'open', forbidden)
            guard.setattr(builtins, 'open', forbidden)
            for route in ('/api/prices', '/api/prices/ORIGINAL-42', '/api/vehicle-cost',
                          '/api/production-cost?vehicles=100', '/api/indices'):
                assert client.get(route).status_code == 200
                assert client.get(route).status_code == 200
            part = client.get('/api/prices/ORIGINAL-42').json()
            assert Decimal(part['prix_unitaire_actuel_eur']) == Decimal('10.25')
            now[0] += 0.1
            changed = client.get('/api/prices/ORIGINAL-42').json()
            assert part['prix_unitaire_actuel_eur'] != changed['prix_unitaire_actuel_eur']
        assert reads == [path, price_data.HISTORY_PATH]
    assert path.read_bytes() == original
