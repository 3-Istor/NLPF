"""Les snapshots de calcul vus depuis l'API (ADR-0014), contre docs/api.md."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from carcost.domain.prices import PriceSnapshot
from carcost.infrastructure.api.app import Repositories, create_app
from fakes import (
    FakeBomRepository,
    FakeCalculationRepository,
    FakeCalculationSnapshotRepository,
    FakeScenarioRepository,
    FakeSnapshotRepository,
    FakeSourcingRepository,
)

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
VERSION = "bom-test"
BASE = "/api/v1/calculation-snapshots"


@pytest.fixture
def repositories(diamond) -> Repositories:
    return Repositories(
        bom=FakeBomRepository(diamond, version=VERSION),
        sourcing=FakeSourcingRepository(),
        snapshots=FakeSnapshotRepository(
            PriceSnapshot(
                id="snp-1", taken_at=NOW, currency="EUR", source="mock",
                prices={"S": Decimal("10.000000")},
            )
        ),
        scenarios=FakeScenarioRepository(),
        calculations=FakeCalculationRepository(),
        calculation_snapshots=FakeCalculationSnapshotRepository(),
        clock=lambda: NOW,
    )


@pytest.fixture
def client(repositories) -> TestClient:
    return TestClient(create_app(repositories))


def make_scenario(client, labour_rate="60.00") -> str:
    response = client.post(
        "/api/v1/scenarios",
        json={
            "bom_version": VERSION,
            "name": "Étude",
            "display_currency": "EUR",
            "labour_rate": labour_rate,
            "parameters": [
                {"part_ref": "S", "supplier_id": "SUP-IT", "plant_id": "PLT-TR"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def freeze(client, scenario_id: str, name: str):
    return client.post(BASE, json={"scenario_id": scenario_id, "name": name})


def test_freezing_returns_the_snapshot_with_its_name_and_copied_parameters(client):
    scenario = make_scenario(client)

    response = freeze(client, scenario["id"], "  Référence T3  ")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Référence T3"
    assert body["scenario_id"] == scenario["id"]
    assert body["scenario_name"] == "Étude"
    assert body["bom_version"] == VERSION
    assert body["price_snapshot_id"] == "snp-1"
    assert body["labour_rate"] == scenario["labour_rate"]
    assert body["active_rules"] == scenario["active_rules"]
    assert body["parameters"] == [
        {k: v for k, v in p.items() if k != "parameter_id"}
        for p in scenario["parameters"]
    ]
    assert body["name_history"][0]["name"] == "Référence T3"
    calculation = client.get(f"/api/v1/calculations/{body['calculation_id']}")
    assert calculation.status_code == 200


def test_a_blank_name_is_refused(client):
    scenario = make_scenario(client)

    response = freeze(client, scenario["id"], "  ")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SNAPSHOT_NAME"


def test_a_taken_name_is_refused_whatever_accents(client):
    scenario = make_scenario(client)
    first = freeze(client, scenario["id"], "Référence T3").json()

    response = freeze(client, scenario["id"], "reference t3")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "SNAPSHOT_NAME_TAKEN"
    assert error["details"]["existing_id"] == first["id"]
    assert error["details"]["name"] == "reference t3"


def test_the_list_shows_the_names_newest_first(client):
    scenario = make_scenario(client)
    freeze(client, scenario["id"], "Premier")
    freeze(client, scenario["id"], "Second")

    body = client.get(BASE, params={"bom_version": VERSION}).json()

    assert body["total"] == 2
    assert [item["name"] for item in body["items"]] == ["Second", "Premier"]
    assert "parameters" not in body["items"][0]
    assert "name_history" not in body["items"][0]


def test_the_list_requires_a_bom_version(client):
    response = client.get(BASE)

    assert response.status_code == 422


def test_renaming_changes_only_the_name(client):
    scenario = make_scenario(client)
    created = freeze(client, scenario["id"], "Ancien").json()

    response = client.patch(f"{BASE}/{created['id']}", json={"name": "Nouveau"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Nouveau"
    assert [h["name"] for h in body["name_history"]] == ["Ancien", "Nouveau"]
    assert {k: v for k, v in body.items() if k not in ("name", "name_history")} == {
        k: v for k, v in created.items() if k not in ("name", "name_history")
    }


def test_renaming_refuses_other_fields(client):
    scenario = make_scenario(client)
    created = freeze(client, scenario["id"], "Ancien").json()

    response = client.patch(
        f"{BASE}/{created['id']}",
        json={"name": "X", "price_snapshot_id": "snp-autre"},
    )

    assert response.status_code == 422
    assert client.get(f"{BASE}/{created['id']}").json() == created


def test_an_unknown_snapshot_is_a_named_404(client):
    response = client.get(f"{BASE}/csn-inconnu")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CALCULATION_SNAPSHOT_NOT_FOUND"


def test_two_snapshots_compare_by_name_without_new_calculation(client, repositories):
    first = freeze(client, make_scenario(client, "60.00")["id"], "Base").json()
    second = freeze(client, make_scenario(client, "90.00")["id"], "Variante").json()
    before = len(repositories.calculations.order)

    response = client.post(
        f"{BASE}/compare",
        json={"snapshot_a_id": first["id"], "snapshot_b_id": second["id"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["snapshot_a"] == {"id": first["id"], "name": "Base"}
    assert body["snapshot_b"] == {"id": second["id"], "name": "Variante"}
    total_a = repositories.calculations.get(first["calculation_id"]).total_cost
    total_b = repositories.calculations.get(second["calculation_id"]).total_cost
    assert total_a != total_b
    assert Decimal(body["total_a"]["amount"]) == total_a
    assert Decimal(body["total_b"]["amount"]) == total_b
    assert len(repositories.calculations.order) == before


def test_snapshots_on_different_price_snapshots_are_not_compared(client, repositories):
    scenario = make_scenario(client)
    first = freeze(client, scenario["id"], "Avant").json()
    repositories.snapshots.snapshots.append(
        PriceSnapshot(
            id="snp-2", taken_at=NOW, currency="EUR", source="mock",
            prices={"S": Decimal("12.000000")},
        )
    )
    second = freeze(client, scenario["id"], "Après").json()
    assert second["price_snapshot_id"] == "snp-2"

    response = client.post(
        f"{BASE}/compare",
        json={"snapshot_a_id": first["id"], "snapshot_b_id": second["id"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INCOMPARABLE_SCENARIOS"


def test_a_scenario_carrying_snapshots_cannot_be_deleted(client):
    scenario = make_scenario(client)
    freeze(client, scenario["id"], "Référence T3")

    response = client.delete(f"/api/v1/scenarios/{scenario['id']}")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "SCENARIO_HAS_SNAPSHOTS"
    assert "Référence T3" in error["message"]
    assert error["details"]["snapshots"] == ["Référence T3"]
    assert client.get(f"/api/v1/scenarios/{scenario['id']}").status_code == 200


def test_freezing_an_unknown_scenario_is_a_named_404(client):
    response = freeze(client, "scn-inconnu", "Gel")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SCENARIO_NOT_FOUND"
