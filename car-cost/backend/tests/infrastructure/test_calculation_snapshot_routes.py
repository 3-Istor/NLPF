"""Les snapshots de calcul vus depuis l'API (ADR-0014), contre docs/api.md."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from carcost.domain.calculation_snapshot import FrozenParameter
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


def derive(client, snapshot_id: str, name: str):
    return client.post(f"{BASE}/{snapshot_id}/derive", json={"name": name})


def test_a_snapshot_says_where_it_came_from(client):
    origin = freeze(client, make_scenario(client)["id"], "Référence T3").json()

    assert origin["derived_from"] is None
    scenario = client.get(f"/api/v1/scenarios/{origin['scenario_id']}").json()
    assert scenario["derived_from"] is None


def test_starting_from_a_snapshot_creates_a_scenario_with_its_copy(client):
    live = make_scenario(client)
    origin = freeze(client, live["id"], "Référence T3").json()
    client.put(
        f"/api/v1/scenarios/{live['id']}/parameters/S",
        json={"scope": "part", "supplier_id": "SUP-DE"},
    )

    response = derive(client, origin["id"], "Référence T3 — repris")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] != live["id"]
    assert body["name"] == "Référence T3 — repris"
    assert body["derived_from"] == origin["id"]
    assert body["bom_version"] == origin["bom_version"]
    assert body["display_currency"] == origin["display_currency"]
    assert body["labour_rate"] == origin["labour_rate"]
    assert body["active_rules"] == origin["active_rules"]
    assert [
        {k: v for k, v in p.items() if k != "parameter_id"}
        for p in body["parameters"]
    ] == origin["parameters"]
    assert client.get(f"{BASE}/{origin['id']}").json() == origin

    recaptured = freeze(client, body["id"], "Référence T3 recapturée").json()
    assert recaptured["derived_from"] == origin["id"]
    assert recaptured["id"] != origin["id"]


def test_settings_that_no_longer_apply_are_refused_with_every_part_named(
    client, repositories,
):
    origin = freeze(client, make_scenario(client)["id"], "Référence T3").json()
    stored = repositories.calculation_snapshots.snapshots[origin["id"]]
    repositories.calculation_snapshots.snapshots[origin["id"]] = replace(
        stored,
        parameters=(
            FrozenParameter(part_ref="S", supplier_id="SUP-DISPARU"),
            FrozenParameter(
                part_ref="S", scope="path", path="V/A/S",
                supplier_id="SUP-IT", plant_id="PLT-DE",
            ),
        ),
    )
    before = len(repositories.scenarios.scenarios)

    response = derive(client, origin["id"], "Référence T3 — repris")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "SNAPSHOT_SETTINGS_NOT_APPLICABLE"
    assert [(p["part_ref"], p["path"]) for p in error["details"]["parts"]] == [
        ("S", None), ("S", "V/A/S"),
    ]
    assert all(p["reason"] for p in error["details"]["parts"])
    assert len(repositories.scenarios.scenarios) == before


def test_starting_from_an_unknown_snapshot_is_a_named_404(client):
    response = derive(client, "csn-inconnu", "Repris")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CALCULATION_SNAPSHOT_NOT_FOUND"


def test_a_blank_name_for_the_derived_scenario_is_refused(client):
    origin = freeze(client, make_scenario(client)["id"], "Référence T3").json()

    response = derive(client, origin["id"], "  ")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SCENARIO"


@pytest.fixture
def frozen_then_changed(client):
    """Un gel réglé sur S, puis le scénario vivant réglé sur A et plus sur S."""
    live = make_scenario(client)
    origin = freeze(client, live["id"], "Référence T3").json()
    client.put(
        f"/api/v1/scenarios/{live['id']}/parameters/A",
        json={"scope": "part", "labour_minutes": "7"},
    )
    on_s = next(p for p in live["parameters"] if p["part_ref"] == "S")
    deleted = client.delete(
        f"/api/v1/scenarios/{live['id']}/parameters/{on_s['parameter_id']}"
    )
    assert deleted.status_code == 200, deleted.text
    return origin


def rows(response) -> dict:
    assert response.status_code == 200, response.text
    return {item["part_ref"]: item for item in response.json()["items"]}


def test_an_open_snapshot_marks_its_rows_from_its_copy(client, frozen_then_changed):
    origin = frozen_then_changed
    tree = f"/api/v1/bom/{VERSION}"
    frozen = {"calculation_snapshot_id": origin["id"]}

    under_root = rows(client.get(f"{tree}/children", params={"path": "V", **frozen}))
    under_a = rows(client.get(f"{tree}/children", params={"path": "V/A", **frozen}))
    root = client.get(f"{tree}/root", params=frozen).json()

    assert under_root["A"]["is_modified"] is False
    assert under_root["A"]["has_modified_descendant"] is True
    assert under_a["S"]["is_modified"] is True
    assert root["has_modified_descendant"] is True
    assert "rolled_up_contribution" in root


def test_without_a_snapshot_the_rows_keep_the_live_marks(client, frozen_then_changed):
    origin = frozen_then_changed
    tree = f"/api/v1/bom/{VERSION}"
    live = {"calculation_id": origin["calculation_id"]}

    under_root = rows(client.get(f"{tree}/children", params={"path": "V", **live}))
    under_a = rows(client.get(f"{tree}/children", params={"path": "V/A", **live}))

    assert under_root["A"]["is_modified"] is True
    assert under_a["S"]["is_modified"] is False


def test_the_snapshot_and_the_calculation_must_agree(client, frozen_then_changed):
    origin = frozen_then_changed
    other = client.post(
        "/api/v1/calculations", json={"scenario_id": origin["scenario_id"]},
    ).json()

    response = client.get(
        f"/api/v1/bom/{VERSION}/root",
        params={"calculation_snapshot_id": origin["id"], "calculation_id": other["id"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CALCULATION_SNAPSHOT_MISMATCH"


def test_an_unknown_open_snapshot_is_a_named_404(client):
    response = client.get(
        f"/api/v1/bom/{VERSION}/root", params={"calculation_snapshot_id": "csn-inconnu"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CALCULATION_SNAPSHOT_NOT_FOUND"
