"""Trois lectures de BOM et une d'indices, puis aucun accès disque ou réseau."""
import builtins
from pathlib import Path
import socket
from unittest.mock import Mock

from fastapi.testclient import TestClient

from carcost.infrastructure.api.app import Repositories, create_app
from carcost.infrastructure.price_data import HISTORY_PATH, MODEL_FILES
from infrastructure.test_price_data import write_models


def test_startup_loads_all_files_once_then_only_uses_memory(tmp_path, monkeypatch):
    write_models(tmp_path)
    original = {p: p.read_bytes() for p in tmp_path.iterdir()}
    reads = []
    original_open = Path.open
    def tracked_open(self, *args, **kwargs):
        reads.append(self)
        return original_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', tracked_open)
    now = [0.0]
    app = create_app(Repositories(bom=Mock()), price_bom_dir=tmp_path,
                     price_clock=lambda: now[0])
    assert reads == []
    def forbidden(*args, **kwargs):
        raise AssertionError('accès disque ou réseau inattendu')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    with TestClient(app) as client:
        expected = [tmp_path / name for name in MODEL_FILES.values()] + [HISTORY_PATH]
        assert reads == expected
        with monkeypatch.context() as guard:
            guard.setattr(Path, 'open', forbidden)
            guard.setattr(builtins, 'open', forbidden)
            for _ in range(3):
                now[0] += 5
                for model in MODEL_FILES:
                    assert client.get('/api/prices', params={'model': model}).status_code == 200
        assert reads == expected
    assert original == {p: p.read_bytes() for p in original}
