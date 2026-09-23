"""Le client de l'API de prix, face au vrai simulateur.

Ces tests démarrent la mock API en mémoire et lui parlent en HTTP. Ils ne
mesurent pas un double : ils mesurent le fichier qui sera lancé en
démonstration, y compris son mode de panne.
"""

from __future__ import annotations

import importlib.util
import threading
from decimal import Decimal
from pathlib import Path

import pytest

from carcost.application.ports import PriceSourceTimeout
from carcost.infrastructure.http_price_source import HttpPriceSource

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "seeds" / "price_catalog.json"
MOCK = ROOT / "price-api" / "mock_price_api.py"


def load_mock_module():
    spec = importlib.util.spec_from_file_location("mock_price_api", MOCK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mock_api():
    """Le simulateur, sur un port libre, lent de 3 s quand on le lui demande."""
    server = load_mock_module().make_server(CATALOG, port=0, slow_seconds=3.0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}"
    server.shutdown()


class TestNominal:
    def test_returns_prices_as_exact_decimals(self, mock_api):
        source = HttpPriceSource(mock_api, timeout_seconds=5.0)

        prices = source.fetch(["FIX-M6-16", "CHS-TIRE-185-65-15"], "EUR")

        assert prices["CHS-TIRE-185-65-15"] == Decimal("42.000000")
        assert isinstance(prices["FIX-M6-16"], Decimal)

    def test_divides_by_the_quantity_the_price_refers_to(self, mock_api):
        """La visserie s'achète par 100 : 3,90 € les cent, pas la pièce.

        Oublier `per` multiplierait par cent le coût de toute la visserie du
        véhicule, sans qu'aucune erreur ne soit levée.
        """
        source = HttpPriceSource(mock_api, timeout_seconds=5.0)

        prices = source.fetch(["FIX-M6-16"], "EUR")

        assert prices["FIX-M6-16"] == Decimal("0.039")

    def test_asks_only_for_what_it_needs(self, mock_api):
        source = HttpPriceSource(mock_api, timeout_seconds=5.0)

        prices = source.fetch(["FIX-M6-16"], "EUR")

        assert list(prices) == ["FIX-M6-16"]

    def test_serves_another_currency(self, mock_api):
        source = HttpPriceSource(mock_api, timeout_seconds=5.0)

        prices = source.fetch(["CHS-TIRE-185-65-15"], "USD")

        assert prices["CHS-TIRE-185-65-15"] != Decimal("42.000000")


class TestTimeout:
    def test_a_silent_api_raises_a_timeout_not_a_network_error(self, mock_api):
        """Le domaine et l'application ne doivent jamais voir passer une
        exception d'urllib : elles ne sauraient pas quoi en faire."""
        source = HttpPriceSource(
            mock_api, timeout_seconds=0.3, failure_mode="timeout"
        )

        with pytest.raises(PriceSourceTimeout):
            source.fetch(["FIX-M6-16"], "EUR")

    def test_it_gives_up_quickly_rather_than_hanging(self, mock_api):
        import time

        source = HttpPriceSource(
            mock_api, timeout_seconds=0.3, failure_mode="timeout"
        )

        started = time.monotonic()
        with pytest.raises(PriceSourceTimeout):
            source.fetch(["FIX-M6-16"], "EUR")

        assert time.monotonic() - started < 2.0


class TestUnreachable:
    def test_a_closed_port_is_reported_as_a_source_failure(self):
        source = HttpPriceSource("http://127.0.0.1:1", timeout_seconds=0.5)

        with pytest.raises(PriceSourceTimeout):
            source.fetch(["FIX-M6-16"], "EUR")
