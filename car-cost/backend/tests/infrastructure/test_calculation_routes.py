"""Scénarios et calculs vus depuis l'API, contre docs/api.md."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from carcost.domain.bom import Bom, Edge
from carcost.domain.prices import PriceSnapshot
from carcost.infrastructure.api.app import Repositories, create_app
from factories import manufactured, purchased
from fakes import (
    FakeBomRepository,
    FakeCalculationRepository,
    FakeScenarioRepository,
    FakeSnapshotRepository,
    FakeSourcingRepository,
)

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
VERSION = "bom-test"


@pytest.fixture
def bom() -> Bom:
    return Bom(
        root_ref="V",
        parts={
            "V": manufactured("V", labour="60"),
            "A": manufactured("A", labour="30"),
            "B": manufactured("B", labour="15"),
            "S": purchased("S"),
        },
        edges=(
            Edge("V", "A", Decimal("2")),
            Edge("V", "B", Decimal("3")),
            Edge("A", "S", Decimal("4")),
            Edge("B", "S", Decimal("5")),
        ),
    )


@pytest.fixture
def repositories(bom) -> Repositories:
    return Repositories(
        bom=FakeBomRepository(bom, version=VERSION),
        sourcing=FakeSourcingRepository(),
        snapshots=FakeSnapshotRepository(
            PriceSnapshot(
                id="snp-1", taken_at=NOW, currency="EUR", source="mock",
                prices={"S": Decimal("10.000000")},
            )
        ),
        scenarios=FakeScenarioRepository(),
        calculations=FakeCalculationRepository(),
        clock=lambda: NOW,
    )


@pytest.fixture
def client(repositories) -> TestClient:
    return TestClient(create_app(repositories))


def make_scenario(client) -> str:
    response = client.post(
        "/api/v1/scenarios",
        json={
            "bom_version": VERSION,
            "name": "test",
            "display_currency": "EUR",
            "labour_rate": "60.00",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestScenario:
    def test_a_new_scenario_has_never_been_calculated(self, client):
        scenario_id = make_scenario(client)

        body = client.get(f"/api/v1/scenarios/{scenario_id}").json()

        assert body["calculation_state"] == "NEVER_RUN"
        assert body["parameters"] == []

    def test_setting_a_parameter_says_what_it_affects(self, client):
        """L'utilisateur doit savoir s'il vient de changer une vis ou douze."""
        scenario_id = make_scenario(client)

        body = client.put(
            f"/api/v1/scenarios/{scenario_id}/parameters/S",
            json={"scope": "part", "supplier_id": "SUP-DE"},
        ).json()

        assert body["scope"] == "part"
        assert body["affects_occurrences"] == 2
        assert body["scope_label"] == "S'applique aux 2 occurrences de cette pièce"

    def test_a_supplier_on_an_assembly_is_refused_by_name(self, client):
        scenario_id = make_scenario(client)

        response = client.put(
            f"/api/v1/scenarios/{scenario_id}/parameters/A",
            json={"scope": "part", "supplier_id": "SUP-DE"},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "PARAMETER_NOT_APPLICABLE"

    def test_a_forced_price_without_justification_is_refused(self, client):
        scenario_id = make_scenario(client)

        response = client.put(
            f"/api/v1/scenarios/{scenario_id}/parameters/S",
            json={"scope": "part", "price_override": "9.99"},
        )

        assert response.status_code == 422
        assert (
            response.json()["error"]["code"]
            == "PRICE_OVERRIDE_JUSTIFICATION_REQUIRED"
        )


class TestCalculation:
    def test_the_total_is_the_hand_computed_value(self, client):
        scenario_id = make_scenario(client)

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert body["total_cost"]["amount"] == "395.000000"
        assert body["total_cost"]["currency"] == "EUR"
        assert body["status"] == "OK"

    def test_the_systems_sum_to_the_total(self, client):
        scenario_id = make_scenario(client)

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert sum(
            Decimal(system["cost"]["amount"]) for system in body["systems"]
        ) == Decimal(body["total_cost"]["amount"])

    def test_it_says_which_prices_it_used_and_how_old_they_are(self, client):
        scenario_id = make_scenario(client)

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert body["price_snapshot"]["id"] == "snp-1"
        assert body["price_snapshot"]["age_seconds"] == 0
        assert body["price_snapshot"]["status"] == "FRESH"

    def test_two_identical_calculations_agree_to_the_cent(self, client):
        scenario_id = make_scenario(client)

        first = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()
        second = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert first["total_cost"] == second["total_cost"]
        assert first["input_digest"] == second["input_digest"]
        assert first["id"] != second["id"]

    def test_the_aggregated_view_sums_to_the_total(self, client):
        scenario_id = make_scenario(client)
        calculation = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        body = client.get(
            f"/api/v1/calculations/{calculation['id']}/aggregated",
            params={"limit": 500},
        ).json()

        assert body["sum_of_own_contributions"]["amount"] == "395.000000"
        assert sum(
            Decimal(item["own_contribution"]["amount"]) for item in body["items"]
        ) == Decimal("395")


class TestStaleness:
    def test_changing_a_parameter_makes_the_totals_obsolete(self, client):
        scenario_id = make_scenario(client)
        client.post("/api/v1/calculations", json={"scenario_id": scenario_id})

        assert (
            client.get(f"/api/v1/scenarios/{scenario_id}").json()["calculation_state"]
            == "UP_TO_DATE"
        )

        client.put(
            f"/api/v1/scenarios/{scenario_id}/parameters/S",
            json={"scope": "part", "supplier_id": "SUP-DE"},
        )

        body = client.get(f"/api/v1/scenarios/{scenario_id}").json()
        assert body["calculation_state"] == "PARAMETERS_CHANGED"
        assert body["stale_reason"] == "parameters"

    def test_recalculating_after_a_change_gives_a_different_total(self, client):
        """Le fournisseur allemand coûte 20 % de plus sur la vis : 23 × 12 = 276,
        plus 165 € de main-d'œuvre, soit 441 €."""
        scenario_id = make_scenario(client)
        client.put(
            f"/api/v1/scenarios/{scenario_id}/parameters/S",
            json={"scope": "part", "supplier_id": "SUP-DE"},
        )

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert body["total_cost"]["amount"] == "441.000000"
        assert (
            client.get(f"/api/v1/scenarios/{scenario_id}").json()["calculation_state"]
            == "UP_TO_DATE"
        )


class TestErrors:
    def test_an_unknown_scenario_is_a_named_404(self, client):
        response = client.post(
            "/api/v1/calculations", json={"scenario_id": "scn-inconnu"}
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "SCENARIO_NOT_FOUND"

    def test_without_a_snapshot_the_calculation_is_refused_not_faked(self, bom):
        empty = Repositories(
            bom=FakeBomRepository(bom, version=VERSION),
            sourcing=FakeSourcingRepository(),
            snapshots=FakeSnapshotRepository(),
            scenarios=FakeScenarioRepository(),
            calculations=FakeCalculationRepository(),
            clock=lambda: NOW,
        )
        client = TestClient(create_app(empty))
        scenario_id = make_scenario(client)

        response = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "NO_PRICE_SNAPSHOT"
