"""Ce que l'API dit d'un snapshot dégradé : le journal, les lignes, le bandeau.

Le backend mettait déjà en quarantaine et retombait sur le dernier prix sain ;
ces tests vérifient que l'écran peut le savoir. Un repli que seul le journal
serveur connaît est un repli silencieux pour l'utilisateur.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from carcost.application.take_snapshot import QuarantinedPrice
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
    """Trois vis sous un ensemble : une saine, une absente, une refusée."""
    screws = ("S", "S-ABSENT", "S-REFUSED")
    return Bom(
        root_ref="V",
        parts={
            "V": manufactured("V", labour="60"),
            "A": manufactured("A", labour="30"),
            **{ref: purchased(ref) for ref in screws},
        },
        edges=(Edge("V", "A", Decimal("2")),)
        + tuple(Edge("A", ref, Decimal("4")) for ref in screws),
    )


@pytest.fixture
def repositories(bom) -> Repositories:
    from dataclasses import replace

    sourcing = FakeSourcingRepository()
    offers = sourcing.sourcing.offers["S"]
    sourcing.sourcing = replace(
        sourcing.sourcing,
        offers={ref: offers for ref in ("S", "S-ABSENT", "S-REFUSED")},
    )

    yesterday = PriceSnapshot(
        id="snp-hier", taken_at=NOW, currency="EUR", source="mock",
        prices={"S": Decimal("10"), "S-ABSENT": Decimal("2"), "S-REFUSED": Decimal("3")},
    )
    today = PriceSnapshot(
        id="snp-jour", taken_at=NOW, currency="EUR", source="mock",
        prices={
            "S": Decimal("10.000000"),
            "S-ABSENT": Decimal("2.000000"),
            "S-REFUSED": Decimal("3.000000"),
        },
        fallback_refs=frozenset({"S-ABSENT", "S-REFUSED"}),
        quarantined_refs=frozenset({"S-REFUSED"}),
    )
    snapshots = FakeSnapshotRepository()
    snapshots.save(yesterday)
    snapshots.save(
        today,
        quarantined=(
            QuarantinedPrice(
                part_ref="S-REFUSED",
                rejected_value="-42.000000",
                reason="prix négatif",
                replacement=Decimal("3.000000"),
            ),
        ),
        previous_id="snp-hier",
    )

    return Repositories(
        bom=FakeBomRepository(bom, version=VERSION),
        sourcing=sourcing,
        snapshots=snapshots,
        scenarios=FakeScenarioRepository(),
        calculations=FakeCalculationRepository(),
        clock=lambda: NOW,
    )


@pytest.fixture
def client(repositories) -> TestClient:
    return TestClient(create_app(repositories))


def calculate(client) -> dict:
    scenario_id = client.post(
        "/api/v1/scenarios",
        json={"bom_version": VERSION, "name": "t", "labour_rate": "60.00"},
    ).json()["id"]
    response = client.post("/api/v1/calculations", json={"scenario_id": scenario_id})
    assert response.status_code == 201, response.text
    return response.json()


class TestDegradedPricesOnTheScreen:
    def lines(self, client, calculation_id) -> dict[str, dict]:
        items = client.get(
            f"/api/v1/bom/{VERSION}/children",
            params={"path": "V/A", "calculation_id": calculation_id},
        ).json()["items"]
        return {item["part_ref"]: item for item in items}

    def test_each_line_says_where_its_price_comes_from(self, client):
        lines = self.lines(client, calculate(client)["id"])

        assert lines["S"]["price_status"] == "OK"
        assert lines["S-ABSENT"]["price_status"] == "FALLBACK"
        assert lines["S-REFUSED"]["price_status"] == "QUARANTINED"

    def test_a_fallback_line_still_shows_its_amount(self, client):
        """8 vis à 3 € par ce chemin : 24 €. Un repli est un prix, pas un trou."""
        lines = self.lines(client, calculate(client)["id"])

        assert lines["S-REFUSED"]["rolled_up_contribution"]["amount"] == "24.000000"

    def test_the_calculation_is_degraded_and_counts_its_lines(self, client):
        body = calculate(client)

        assert body["status"] == "DEGRADED"
        assert body["price_snapshot"]["status"] == "DEGRADED"
        assert body["issue_counts"] == {
            "missing_price": 0,
            "quarantined": 1,
            "fallback": 1,
        }

    def test_a_calculation_read_again_says_the_same(self, client):
        calculation_id = calculate(client)["id"]

        body = client.get(f"/api/v1/calculations/{calculation_id}").json()

        assert body["issue_counts"]["quarantined"] == 1
