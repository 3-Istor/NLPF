"""Les réglages sauvegardés restent accessibles sans calcul ni prix."""

import pytest
from fastapi.testclient import TestClient

from carcost.infrastructure.api.app import Repositories, create_app
from fakes import (
    FakeBomRepository, FakeCalculationRepository, FakeScenarioRepository,
    FakeSnapshotRepository, FakeSourcingRepository,
)


@pytest.fixture
def repositories(diamond):
    return Repositories(
        bom=FakeBomRepository(diamond), scenarios=FakeScenarioRepository(),
        sourcing=FakeSourcingRepository(), snapshots=FakeSnapshotRepository(),
        calculations=FakeCalculationRepository(),
    )


@pytest.fixture
def client(repositories):
    return TestClient(create_app(repositories))


def payload(**changes):
    return {
        "bom_version": "bom-test", "name": "Base été — synthétique",
        "display_currency": "EUR", "labour_rate": "42.123456", "active_rules": [],
        "parameters": [
            {"part_ref": "S", "supplier_id": "SUP-IT", "plant_id": "PLT-TR",
             "purchase_currency": "USD", "price_override": "9.123456",
             "price_override_justification": "Offre négociée synthétique"},
            {"part_ref": "A", "labour_minutes": "21.2345"},
            {"part_ref": "S", "scope": "path", "path": "V/B/S",
             "supplier_id": "SUP-DE", "plant_id": "PLT-DE", "purchase_currency": "RUB"},
        ],
        **changes,
    }


def create(client, **changes):
    response = client.post("/api/v1/scenarios", json=payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def test_full_scenario_round_trip(client):
    saved = create(client)
    reloaded = client.get(f"/api/v1/scenarios/{saved['id']}").json()

    assert reloaded == saved
    assert reloaded["name"] == payload()["name"]
    assert reloaded["active_rules"] == []
    assert reloaded["labour_rate"] == "42.123456"
    parameters = {p["path"] or p["part_ref"]: p for p in reloaded["parameters"]}
    assert parameters["S"]["scope"] == "part"
    assert parameters["S"]["purchase_currency"] == "USD"
    assert parameters["S"]["supplier_id"] == "SUP-IT"
    assert parameters["S"]["plant_id"] == "PLT-TR"
    assert parameters["S"]["price_override"] == "9.123456"
    assert parameters["S"]["price_override_justification"] == "Offre négociée synthétique"
    assert parameters["A"]["labour_minutes"] == "21.2345"
    assert parameters["V/B/S"]["purchase_currency"] == "RUB"


def test_parameter_ids_can_be_recovered_after_reloading_scenario(client):
    saved = create(client)

    reloaded = client.get(f"/api/v1/scenarios/{saved['id']}").json()

    identifiers = {
        parameter["path"] or parameter["part_ref"]: parameter["parameter_id"]
        for parameter in reloaded["parameters"]
    }
    assert all(identifier.startswith("prm-") for identifier in identifiers.values())
    response = client.delete(
        f"/api/v1/scenarios/{saved['id']}/parameters/{identifiers['S']}"
    )
    assert response.status_code == 200


def test_scenarios_can_be_listed_newest_first(client):
    first = create(client, name="Premier")
    second = create(client, name="Deuxième")

    response = client.get("/api/v1/scenarios")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "items": [second, first],
        "total": 2,
    }


def test_scenario_can_be_deleted(client):
    saved = create(client)

    response = client.delete(f"/api/v1/scenarios/{saved['id']}")

    assert response.status_code == 204, response.text
    assert response.content == b""
    missing = client.get(f"/api/v1/scenarios/{saved['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SCENARIO_NOT_FOUND"


def test_deleting_unknown_scenario_is_explicit(client):
    response = client.delete("/api/v1/scenarios/scn-unknown")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SCENARIO_NOT_FOUND"


def test_duplicate_can_be_modified_without_changing_source(client):
    original = create(client)
    response = client.post(
        f"/api/v1/scenarios/{original['id']}/duplicate", json={"name": "Alternative"},
    )
    assert response.status_code == 201, response.text
    copied = response.json()
    assert copied["id"] != original["id"]
    assert copied["name"] == "Alternative"
    assert [
        {key: value for key, value in parameter.items() if key != "parameter_id"}
        for parameter in copied["parameters"]
    ] == [
        {key: value for key, value in parameter.items() if key != "parameter_id"}
        for parameter in original["parameters"]
    ]
    assert {
        parameter["parameter_id"] for parameter in copied["parameters"]
    }.isdisjoint(
        parameter["parameter_id"] for parameter in original["parameters"]
    )
    assert copied["active_rules"] == original["active_rules"]
    assert copied["labour_rate"] == original["labour_rate"]
    response = client.put(
        f"/api/v1/scenarios/{copied['id']}/parameters/S",
        json={"purchase_currency": "EUR", "supplier_id": "SUP-DE"},
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/api/v1/scenarios/{original['id']}").json() == original
    assert client.get(f"/api/v1/scenarios/{copied['id']}").json()["parameters"] != original["parameters"]


def test_unknown_part_is_rejected_without_snapshot_and_leaves_no_trace(client, repositories):
    original = create(client)
    response = client.put(
        f"/api/v1/scenarios/{original['id']}/parameters/UNKNOWN",
        json={"purchase_currency": "USD"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PARAMETER_NOT_APPLICABLE"
    assert "UNKNOWN" in response.json()["error"]["message"]
    assert client.get(f"/api/v1/scenarios/{original['id']}").json() == original

    response = client.post(
        "/api/v1/scenarios", json=payload(parameters=[{"part_ref": "UNKNOWN"}]),
    )
    assert response.status_code == 422
    assert len(repositories.scenarios.scenarios) == 1


def test_path_target_and_part_target_coexist_and_path_update_is_local(client):
    original = create(client)
    for path in ("V/A/S", "V/B/S"):
        response = client.put(
            f"/api/v1/scenarios/{original['id']}/parameters/{path}",
            json={"scope": "path", "purchase_currency": "EUR"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["affects_occurrences"] == 1
        assert response.json()["scope_label"] == "S'applique à cette occurrence uniquement"
    saved = client.get(f"/api/v1/scenarios/{original['id']}").json()
    parameters = {p["path"] or p["part_ref"]: p for p in saved["parameters"]}
    assert parameters["S"]["purchase_currency"] == "USD"
    assert parameters["V/A/S"]["purchase_currency"] == "EUR"
    assert parameters["V/B/S"]["purchase_currency"] == "EUR"
    assert len(parameters) == 4


@pytest.mark.parametrize("target,parameter", [
    ("S", {"scope": "other"}),
    ("S", {"scope": "path"}),
    ("S", {"scope": "part", "path": "V/A/S"}),
    ("V/S", {"scope": "path"}),
    ("V/A/S", {"scope": "path", "path": "V/B/S"}),
    ("V/A/S", {"scope": "part"}),
])
def test_invalid_scope_or_path_is_rejected_before_writing(client, target, parameter):
    original = create(client)
    response = client.put(
        f"/api/v1/scenarios/{original['id']}/parameters/{target}", json=parameter,
    )
    assert response.status_code == 422, response.text
    assert client.get(f"/api/v1/scenarios/{original['id']}").json() == original


@pytest.mark.parametrize("parameter,code", [
    ({"supplier_id": "UNKNOWN"}, "NO_SUPPLIER_FOR_PART"),
    ({"supplier_id": "SUP-IT", "plant_id": "PLT-DE"}, "PLANT_NOT_AVAILABLE_FOR_SUPPLIER"),
    ({"price_override": "9"}, "PRICE_OVERRIDE_JUSTIFICATION_REQUIRED"),
    ({"labour_minutes": "5"}, "PARAMETER_NOT_APPLICABLE"),
])
def test_validation_does_not_depend_on_prices(client, parameter, code):
    original = create(client)
    response = client.put(
        f"/api/v1/scenarios/{original['id']}/parameters/S", json=parameter,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code
    assert client.get(f"/api/v1/scenarios/{original['id']}").json() == original


def test_unknown_bom_is_rejected_before_creation(client, repositories):
    response = client.post("/api/v1/scenarios", json=payload(bom_version="UNKNOWN"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BOM_VERSION_NOT_FOUND"
    assert repositories.scenarios.scenarios == {}


def test_unknown_source_cannot_be_duplicated(client):
    response = client.post("/api/v1/scenarios/UNKNOWN/duplicate", json={"name": "Copie"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SCENARIO_NOT_FOUND"


@pytest.mark.parametrize("name", ["", "   "])
def test_empty_name_is_refused_for_creation_and_duplication(client, repositories, name):
    response = client.post("/api/v1/scenarios", json=payload(name=name))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SCENARIO"
    assert repositories.scenarios.scenarios == {}
    original = create(client)
    response = client.post(
        f"/api/v1/scenarios/{original['id']}/duplicate", json={"name": name},
    )
    assert response.status_code == 422
    assert len(repositories.scenarios.scenarios) == 1


def test_parameter_identity_is_stable_and_cannot_delete_another_scenario_setting(client):
    original = create(client)
    target = f"/api/v1/scenarios/{original['id']}/parameters/S"
    first = client.put(target, json={"purchase_currency": "EUR"}).json()
    second = client.put(target, json={"purchase_currency": "USD"}).json()
    assert first["parameter_id"] == second["parameter_id"]
    copied = client.post(
        f"/api/v1/scenarios/{original['id']}/duplicate", json={"name": "Copie"},
    ).json()
    response = client.delete(
        f"/api/v1/scenarios/{copied['id']}/parameters/{first['parameter_id']}",
    )
    assert response.status_code == 200
    assert client.get(f"/api/v1/scenarios/{copied['id']}").json() == copied


class TestAfterSales:
    def test_a_new_scenario_does_not_count_spares(self, client):
        saved = create(client)
        assert saved["include_after_sales"] is False
        # Le losange de test n'a aucune pièce de rechange.
        assert saved["after_sales_available"] is False

    def test_switching_spares_is_saved(self, client):
        saved = create(client)
        response = client.patch(
            f"/api/v1/scenarios/{saved['id']}", json={"include_after_sales": True}
        )
        assert response.status_code == 200, response.text
        assert response.json()["include_after_sales"] is True
        reloaded = client.get(f"/api/v1/scenarios/{saved['id']}").json()
        assert reloaded["include_after_sales"] is True

    def test_an_unknown_scenario_is_named(self, client):
        response = client.patch(
            "/api/v1/scenarios/scn-inconnu", json={"include_after_sales": True}
        )
        assert response.status_code == 404
