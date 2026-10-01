"""Parcours HTTP complet : scénario, calcul, comparaison, recommandation."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from carcost.domain.prices import PriceSnapshot
from carcost.infrastructure.api.app import Repositories, create_app
from fakes import (
    FakeBomRepository,
    FakeCalculationRepository,
    FakeScenarioRepository,
    FakeSnapshotRepository,
    FakeSourcingRepository,
)

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def client(diamond):
    repositories = Repositories(
        bom=FakeBomRepository(diamond),
        sourcing=FakeSourcingRepository(),
        snapshots=FakeSnapshotRepository(
            PriceSnapshot(
                id="snp", taken_at=NOW, currency="EUR", source="test",
                prices={"S": Decimal("10")},
            )
        ),
        scenarios=FakeScenarioRepository(),
        calculations=FakeCalculationRepository(),
        clock=lambda: NOW,
    )
    return TestClient(create_app(repositories))


def create_scenario(client, name, parameters=()):
    response = client.post(
        "/api/v1/scenarios",
        json={
            "bom_version": "bom-test",
            "name": name,
            "display_currency": "EUR",
            "labour_rate": "60",
            "parameters": list(parameters),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_compare_endpoint_uses_one_snapshot_and_explains_exact_delta(client):
    baseline = create_scenario(client, "Base")
    alternative = create_scenario(
        client,
        "Turquie",
        ({"part_ref": "S", "supplier_id": "SUP-IT", "plant_id": "PLT-TR"},),
    )

    response = client.post(
        "/api/v1/scenarios/compare",
        json={
            "scenario_a_id": baseline,
            "scenario_b_id": alternative,
            "price_snapshot_id": "snp",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cost_delta"]["amount"] == "-23.000000"
    assert body["price_snapshot_id"] == "snp"
    assert body["top_differences"][0]["part_ref"] == "S"
    assert body["top_differences"][0]["delta"]["amount"] == "-23.000000"
    # PLT-IT transporte à 0.021, PLT-TR à 0.142 kg CO2e/kg ; S pèse 1 kg et sa
    # quantité cumulée est 23 : (0.142 - 0.021) × 1 × 23 = 2.783.
    assert body["co2_delta_kg"] == "2.783000"


def test_recommendation_creates_a_calculable_optimized_scenario(client):
    baseline = create_scenario(client, "Base")

    response = client.post(
        f"/api/v1/scenarios/{baseline}/recommend-sourcing",
        json={"name": "Optimisé", "price_snapshot_id": "snp"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["savings"]["amount"] == "23.000000"
    assert body["recommendations"][0]["part_ref"] == "S"
    assert body["recommendations"][0]["accepted"] is True
    assert body["recommendations"][0]["recommended"]["origin_country"] == "TR"
    optimized = body["optimized_scenario"]
    assert optimized["id"] != baseline
    assert optimized["parameters"][0]["plant_id"] == "PLT-TR"


def test_a_scenario_names_its_last_calculation(client):
    """Rouvrir un scénario « à jour » doit pouvoir montrer son total sans
    relancer un calcul : l'écran relit celui que le serveur désigne."""
    scenario = create_scenario(client, "Base")
    assert client.get(f"/api/v1/scenarios/{scenario}").json()["last_calculation_id"] is None

    calculation = client.post(
        "/api/v1/calculations", json={"scenario_id": scenario, "price_snapshot_id": "snp"}
    ).json()

    reread = client.get(f"/api/v1/scenarios/{scenario}").json()
    assert reread["last_calculation_id"] == calculation["id"]
    assert reread["calculation_state"] == "UP_TO_DATE"


def test_preview_explains_recommendations_without_creating_a_scenario(client):
    """L'écran montre les lignes, l'utilisateur coche, puis seulement on crée.

    Sans aperçu, choisir les lignes obligerait à créer une variante pour voir
    la liste, puis une seconde avec la sélection : une variante fantôme par
    essai, dans la liste des scénarios de l'utilisateur.
    """
    baseline = create_scenario(client, "Base")
    before = client.get("/api/v1/scenarios").json()["total"]

    response = client.post(
        f"/api/v1/scenarios/{baseline}/recommend-sourcing/preview",
        json={"price_snapshot_id": "snp", "forbidden_origins": ["de"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["base_scenario_id"] == baseline
    assert body["constraints"]["forbidden_origins"] == ["DE"]
    assert body["price_snapshot_id"] == "snp"
    assert [item["part_ref"] for item in body["recommendations"]] == ["S"]
    assert body["recommendations"][0]["estimated_saving"]["amount"] == "23.000000"
    assert body["unresolved"] == []
    assert "optimized_scenario" not in body
    assert client.get("/api/v1/scenarios").json()["total"] == before


def test_recommendation_can_be_accepted_partially_by_part(client):
    baseline = create_scenario(client, "Base")

    response = client.post(
        f"/api/v1/scenarios/{baseline}/recommend-sourcing",
        json={
            "name": "Sélection vide",
            "accepted_part_refs": [],
            "price_snapshot_id": "snp",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["savings"]["amount"] == "0.000000"
    assert body["recommendations"][0]["accepted"] is False
    assert body["optimized_scenario"]["parameters"] == []


def test_forbidden_origin_is_visible_and_respected(client):
    baseline = create_scenario(client, "Base")

    response = client.post(
        f"/api/v1/scenarios/{baseline}/recommend-sourcing",
        json={
            "name": "Sans Turquie",
            "forbidden_origins": ["tr"],
            "price_snapshot_id": "snp",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["constraints"]["forbidden_origins"] == ["TR"]
    assert body["recommendations"] == []
    assert body["unresolved"] == []
    assert body["savings"]["amount"] == "0.000000"


def test_a_violation_without_remedy_is_named_in_the_response(client):
    baseline = create_scenario(client, "Base")

    response = client.post(
        f"/api/v1/scenarios/{baseline}/recommend-sourcing",
        json={
            "name": "Tout interdit",
            "forbidden_origins": ["IT", "TR", "DE"],
            "price_snapshot_id": "snp",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recommendations"] == []
    assert [item["part_ref"] for item in body["unresolved"]] == ["S"]
    assert body["unresolved"][0]["current"]["origin_country"] == "IT"


def test_invalid_origin_constraint_is_rejected(client):
    baseline = create_scenario(client, "Base")

    response = client.post(
        f"/api/v1/scenarios/{baseline}/recommend-sourcing",
        json={"name": "Invalide", "forbidden_origins": ["France"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SCENARIO"
