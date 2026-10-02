"""Prix en direct, prix figés depuis l'écran, historique d'une pièce (ADR-0015)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from carcost.application.ports import (
    PriceHistory,
    PriceNotQuoted,
    PricePoint,
    PriceSourceTimeout,
    Quote,
)
from carcost.infrastructure.api.app import Repositories, create_app
from fakes import (
    FakeBomRepository,
    FakeCalculationRepository,
    FakeScenarioRepository,
    FakeSnapshotRepository,
    FakeSourcingRepository,
)

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc)


class MovingPrices:
    """Une source dont le prix change à chaque appel, comme le marché simulé."""

    name = "price-api"

    def __init__(self) -> None:
        self.price = Decimal("10")
        self.silent = False

    def fetch(self, refs, currency):
        if self.silent:
            raise PriceSourceTimeout("aucune réponse en 2 s")
        self.price += 1
        return [Quote(ref, self.price, str(self.price)) for ref in refs]

    def history(self, ref, currency):
        if ref != "S":
            raise PriceNotQuoted(ref)
        return PriceHistory(
            part_ref=ref, currency=currency, unit="pce", reference=Decimal("10"),
            points=(PricePoint("2026-01-01", Decimal("10")), PricePoint("2026-01-02", Decimal("11"))),
            now_at="2026-01-02T00:00:00+00:00", now_price=Decimal("11"),
            profile="steel", drivers={"acier": Decimal("0.62")}, origin_currency=None,
        )


@pytest.fixture
def prices():
    return MovingPrices()


@pytest.fixture
def repositories(diamond, prices):
    return Repositories(
        bom=FakeBomRepository(diamond), sourcing=FakeSourcingRepository(),
        snapshots=FakeSnapshotRepository(), scenarios=FakeScenarioRepository(),
        calculations=FakeCalculationRepository(), clock=lambda: NOW, prices=prices,
    )


@pytest.fixture
def client(repositories):
    return TestClient(create_app(repositories))


@pytest.fixture
def scenario_id(client):
    response = client.post(
        "/api/v1/scenarios",
        json={"bom_version": "bom-test", "name": "t", "labour_rate": "60.00"},
    )
    return response.json()["id"]


class TestLive:
    def test_prices_move_between_two_live_calculations(self, client, scenario_id):
        first = client.post("/api/v1/calculations/live", json={"scenario_id": scenario_id})
        second = client.post("/api/v1/calculations/live", json={"scenario_id": scenario_id})
        assert first.status_code == 200, first.text
        assert first.json()["price_mode"] == "LIVE"
        assert first.json()["total_cost"] != second.json()["total_cost"]

    def test_nothing_is_recorded(self, client, scenario_id, repositories):
        client.post("/api/v1/calculations/live", json={"scenario_id": scenario_id})
        assert repositories.snapshots.snapshots == []
        assert repositories.calculations.latest_for(scenario_id) is None
        scenario = client.get(f"/api/v1/scenarios/{scenario_id}").json()
        assert scenario["last_calculation_id"] is None

    def test_the_tree_can_still_read_a_live_calculation(self, client, scenario_id):
        live = client.post(
            "/api/v1/calculations/live", json={"scenario_id": scenario_id}
        ).json()
        response = client.get(f"/api/v1/calculations/{live['id']}")
        assert response.status_code == 200
        assert response.json()["total_cost"] == live["total_cost"]

    def test_a_silent_api_is_said_not_replaced(self, client, scenario_id, prices):
        prices.silent = True
        response = client.post("/api/v1/calculations/live", json={"scenario_id": scenario_id})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "PRICE_SOURCE_UNAVAILABLE"


class TestFreezePrices:
    def test_freezing_records_a_snapshot_of_this_bom(self, client, repositories):
        response = client.post("/api/v1/price-snapshots", json={"bom_version": "bom-test"})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["bom_version"] == "bom-test"
        assert body["counts"]["prices"] == 1
        assert repositories.snapshots.latest("bom-test").id == body["id"]

    def test_a_calculation_after_freezing_uses_the_frozen_prices(
        self, client, scenario_id
    ):
        frozen = client.post("/api/v1/price-snapshots", json={"bom_version": "bom-test"}).json()
        calculation = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()
        assert calculation["price_snapshot"]["id"] == frozen["id"]
        assert calculation["price_mode"] == "SNAPSHOT"

    def test_a_silent_api_creates_nothing(self, client, repositories, prices):
        client.post("/api/v1/price-snapshots", json={"bom_version": "bom-test"})
        prices.silent = True
        response = client.post("/api/v1/price-snapshots", json={"bom_version": "bom-test"})
        assert response.status_code == 503
        assert len(repositories.snapshots.snapshots) == 1

    def test_without_a_price_api_the_route_says_so(self, diamond):
        client = TestClient(create_app(Repositories(
            bom=FakeBomRepository(diamond), snapshots=FakeSnapshotRepository(),
        )))
        response = client.post("/api/v1/price-snapshots", json={"bom_version": "bom-test"})
        assert response.status_code == 503


class TestPriceHistory:
    def test_gives_the_simulated_year_and_the_frozen_prices(self, client):
        client.post("/api/v1/price-snapshots", json={"bom_version": "bom-test"})
        body = client.get("/api/v1/bom/bom-test/parts/S/price-history").json()
        assert [p["price"] for p in body["points"]] == ["10", "11"]
        assert body["profile"] == "steel"
        assert len(body["snapshots"]) == 1
        assert body["is_synthetic"] is True

    def test_an_assembly_has_no_price_to_chart(self, client):
        response = client.get("/api/v1/bom/bom-test/parts/A/price-history")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PART_HAS_NO_PRICE"

    def test_an_unknown_part_is_named(self, client):
        response = client.get("/api/v1/bom/bom-test/parts/NOPE/price-history")
        assert response.status_code == 404
