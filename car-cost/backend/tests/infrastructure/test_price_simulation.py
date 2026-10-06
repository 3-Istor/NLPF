"""L'année de marché simulée par la mock API, et sa route `/history`.

Comme les tests du client HTTP, ils chargent le fichier qui sera lancé en
démonstration, pas un double.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import urllib.request
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "price-api"
INDICES = API / "data" / "price_indices.json"


def _load(name: str):
    sys.path.insert(0, str(API))
    spec = importlib.util.spec_from_file_location(name, API / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


simulation = _load("simulation")
mock = _load("mock_price_api")


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def market(clock):
    # Une année en 73 minutes : un jour simulé dure exactement 12 secondes.
    return simulation.Market(INDICES, year_minutes=73, clock=clock)


DAY = 12


ENTRY = {
    "price_per": "1",
    "unit": "pce",
    "drivers": {"acier": "0.62", "energie": "0.25", "transport": "0.13"},
    "prices": {"EUR": {"reference": "100.000000"}, "GBP": {"reference": "85.000000"}},
}


def _expected_factor(day: int) -> Decimal:
    indices = json.loads(INDICES.read_text(encoding="utf-8"))["indices"]
    return 1 + sum(
        Decimal(w) * (Decimal(indices[n][day]) / Decimal(indices[n][0]) - 1)
        for n, w in ENTRY["drivers"].items()
    )


class TestMarket:
    def test_without_a_clock_prices_stay_at_their_reference(self):
        frozen = simulation.Market(INDICES)
        assert frozen.position() == 0
        assert frozen.price(ENTRY, "EUR", frozen.position()) == Decimal("100.000000")

    def test_a_day_later_the_price_follows_its_indices(self, market, clock):
        clock.now += 30 * DAY
        position = market.position()
        assert position == 30
        expected = (Decimal(100) * _expected_factor(30)).quantize(Decimal("0.000001"))
        assert market.price(ENTRY, "EUR", position) == expected

    def test_between_two_days_the_index_is_interpolated(self, market):
        halfway = (market.index("acier", Decimal(10)) + market.index("acier", Decimal(11))) / 2
        assert market.index("acier", Decimal("10.5")) == halfway

    def test_the_year_loops_without_a_jump(self, market, clock):
        """Du jour 364 au jour 0, la courbe rejoint son départ au lieu de sauter."""
        clock.now += 365 * DAY
        assert market.position() == 0
        between = market.index("cuivre", Decimal("364.5"))
        last, first = market.indices["cuivre"][364], market.indices["cuivre"][0]
        assert between == (last + first) / 2

    def test_a_british_supplier_keeps_its_pound_price_and_the_euro_follows_the_rate(
        self, market
    ):
        british = {**ENTRY, "origin_currency": "GBP"}
        day = Decimal(100)
        material_only = market.price(ENTRY, "GBP", day)
        assert market.price(british, "GBP", day) == material_only
        assert market.price(british, "EUR", day) == (
            Decimal(100) * market.factor(ENTRY["drivers"], day) * market.fx_change(day)
        ).quantize(Decimal("0.000001"))

    def test_history_has_one_point_per_simulated_day(self, market, clock):
        clock.now += 42 * DAY
        history = market.history(ENTRY, "EUR")
        assert len(history["points"]) == 365
        assert history["points"][0] == {"date": "2026-01-01", "price": "100.000000"}
        assert history["now"]["day"] == "42.000"
        assert history["now"]["price"] == history["points"][42]["price"]

    def test_two_parts_with_the_same_drivers_move_differently(self, market):
        """La part propre : même profil, courbes distinctes, départ et bouclage intacts."""
        one = [p["price"] for p in market.history(ENTRY, "EUR", "REF-A")["points"]]
        other = [p["price"] for p in market.history(ENTRY, "EUR", "REF-B")["points"]]
        assert one[0] == other[0] == "100.000000"
        assert one != other
        assert one == [p["price"] for p in market.history(ENTRY, "EUR", "REF-A")["points"]]
        assert abs(simulation.wobble("REF-A", Decimal(365))) < Decimal("1e-9")

    def test_the_catalog_bounds_hold_the_curve(self, market):
        """Le creux de l'année touche `year_min`, le sommet `year_max`, le jour 0 la référence."""
        bounded = {
            **ENTRY,
            "prices": {"EUR": {"reference": "100.000000", "year_min": "80.000000",
                               "year_max": "130.000000"}},
        }
        prices = [Decimal(p["price"]) for p in market.history(bounded, "EUR", "REF-A")["points"]]
        assert prices[0] == Decimal("100.000000")
        assert min(prices) == Decimal("80.000000")
        assert max(prices) == Decimal("130.000000")
        assert Decimal(80) <= market.price(bounded, "EUR", Decimal("364.5"), "REF-A") <= 130


class TestCatalogs:
    def test_the_four_boms_are_served_together(self):
        catalog = mock.PriceCatalog(mock.default_catalogs(ROOT / "seeds"))
        assert "FIX-M6-16" in catalog.prices
        assert "VALH-BOM-0004" in catalog.prices
        assert "VALE-BOM-0006-PEAU-EXT" in catalog.prices

    def test_two_catalogs_quoting_the_same_part_are_refused(self, tmp_path):
        catalog = ROOT / "seeds" / "price_catalog.json"
        with pytest.raises(ValueError, match="déjà cotées"):
            mock.PriceCatalog([catalog, catalog])


@pytest.fixture
def served(market):
    server = mock.make_server(
        mock.default_catalogs(ROOT / "seeds"), port=0, market=market
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}"
    server.shutdown()


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as refused:
        return refused.code, json.loads(refused.read())


class TestHistoryRoute:
    def test_serves_the_year_of_a_part(self, served, clock):
        clock.now += 12 * DAY
        status, body = _get(f"{served}/history?ref=VALH-BOM-0006-PEAU-EXT&currency=EUR")
        assert status == 200
        assert body["is_synthetic"] is True
        assert len(body["points"]) == 365
        assert body["profile"] == "composite"
        assert body["now"]["price"] == body["points"][12]["price"]

    def test_an_unknown_part_is_named(self, served):
        status, body = _get(f"{served}/history?ref=NOPE&currency=EUR")
        assert status == 404
        assert body["error"]["code"] == "UNKNOWN_REF"

    def test_prices_carry_the_simulated_date(self, served, clock):
        clock.now += 31 * DAY
        status, body = _get(f"{served}/prices?refs=VALH-BOM-0006-PEAU-EXT&currency=EUR")
        assert status == 200
        assert body["as_of"].startswith("2026-02-01")


class TestHttpHistory:
    def test_the_client_brings_the_curve_back_to_one_unit(self, served):
        """La visserie se cote par 100 : la courbe aussi, et le client la
        ramène à la pièce une fois, comme une cotation."""
        from carcost.infrastructure.http_price_source import HttpPriceSource

        history = HttpPriceSource(served).history("FIX-M6-16", "EUR")
        assert history.reference == Decimal("0.039")
        assert history.points[0].price == Decimal("0.039")
        assert len(history.points) == 365

    def test_an_unquoted_part_is_not_a_breakdown(self, served):
        from carcost.application.ports import PriceNotQuoted
        from carcost.infrastructure.http_price_source import HttpPriceSource

        with pytest.raises(PriceNotQuoted):
            HttpPriceSource(served).history("NOPE", "EUR")
