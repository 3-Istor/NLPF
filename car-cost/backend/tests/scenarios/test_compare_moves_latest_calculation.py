"""Caractérisation : comparer déplace le dernier calcul du scénario A.

Défaut connu, pas comportement voulu : `POST /scenarios/compare` enregistre de
nouveaux calculs, et celui du scénario A devient son `last_calculation_id`. Le
calcul demandé explicitement est relégué. Dette « Comparer et recommander
enregistrent de nouveaux calculs » du README, corrigée en lot 2.3 ; ce test
devra alors changer.
"""

from datetime import datetime, timezone
from decimal import Decimal

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


def create_scenario(client, name):
    response = client.post(
        "/api/v1/scenarios",
        json={
            "bom_version": "bom-test",
            "name": name,
            "display_currency": "EUR",
            "labour_rate": "60",
            "parameters": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_comparing_makes_the_comparison_calculation_the_latest(diamond):
    client = TestClient(
        create_app(
            Repositories(
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
        )
    )
    a = create_scenario(client, "Base")
    b = create_scenario(client, "Variante")
    calc1 = client.post(
        "/api/v1/calculations", json={"scenario_id": a, "price_snapshot_id": "snp"}
    ).json()["id"]

    comparison = client.post(
        "/api/v1/scenarios/compare",
        json={"scenario_a_id": a, "scenario_b_id": b, "price_snapshot_id": "snp"},
    ).json()

    latest = client.get(f"/api/v1/scenarios/{a}").json()["last_calculation_id"]
    assert latest == comparison["calculation_a_id"]
    assert latest != calc1
