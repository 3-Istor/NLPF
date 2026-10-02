"""Les routes de lecture du graphe, contre le contrat de docs/api.md."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from datetime import datetime, timezone

from carcost.application.ports import (
    BomVersionNotFound,
    BomVersionNotValidated,
    BomVersionSummary,
)
from carcost.domain.bom import Bom, Edge
from carcost.infrastructure.api.app import Repositories, create_app
from carcost.application.price_resolution import resolve_unit_prices
from carcost.application.run_calculation import run_calculation
from carcost.application.scenario import Scenario
from carcost.domain.prices import PriceSnapshot
from factories import manufactured, purchased
from fakes import (
    FakeCalculationRepository,
    FakeScenarioRepository,
    FakeSourcingRepository,
)

VERSION = "bom-test"


class FakeRepository:
    """Un dépôt en mémoire : les routes se testent sans Postgres."""

    def __init__(self, bom: Bom, *, validated: bool = True):
        self.bom = bom
        self.validated = validated
        self.loads = 0

    def load(self, version: str) -> Bom:
        self.loads += 1
        if version != VERSION:
            raise BomVersionNotFound(version)
        if not self.validated:
            raise BomVersionNotValidated(version)
        return self.bom

    def versions(self):
        return (
            BomVersionSummary(
                id=VERSION,
                label="Losange de test",
                root_part_ref="V",
                part_count=4,
                edge_count=4,
                validated_at=(
                    datetime(2026, 9, 22, 10, 4, 11, tzinfo=timezone.utc)
                    if self.validated
                    else None
                ),
                is_synthetic=True,
            ),
        )


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
def client(bom) -> TestClient:
    return TestClient(create_app(Repositories(bom=FakeRepository(bom))))


class TestUnfolding:
    def test_the_root_comes_with_a_path(self, client):
        body = client.get(f"/api/v1/bom/{VERSION}/root").json()

        assert body["path"] == "V"
        assert body["has_children"] is True

    def test_unfolding_returns_direct_children_only(self, client):
        body = client.get(
            f"/api/v1/bom/{VERSION}/children", params={"path": "V"}
        ).json()

        assert [item["part_ref"] for item in body["items"]] == ["A", "B"]
        assert all("S" not in item["path"] for item in body["items"])

    def test_there_is_no_depth_parameter_to_pull_the_whole_graph(self, client):
        """La route ne permet pas de tout charger d'un coup : c'est la
        contrainte, pas une valeur par défaut qu'on pourrait changer."""
        response = client.get(
            f"/api/v1/bom/{VERSION}/children", params={"path": "V", "depth": 99}
        )

        assert response.status_code == 200
        assert [i["part_ref"] for i in response.json()["items"]] == ["A", "B"]

    def test_a_shared_part_carries_its_count_of_places(self, client):
        body = client.get(
            f"/api/v1/bom/{VERSION}/children", params={"path": "V/A"}
        ).json()

        assert body["items"][0]["occurrence_count"] == 2
        assert body["items"][0]["parent_count"] == 2


class TestNumbersOnTheWire:
    def test_quantities_travel_as_strings_not_floats(self, client):
        """Un nombre flottant en JSON, et la reproductibilité au centime
        n'est plus démontrable (ADR-0011)."""
        raw = client.get(
            f"/api/v1/bom/{VERSION}/children", params={"path": "V/A"}
        ).text

        assert '"edge_quantity":"4.000000"' in raw.replace(" ", "")

    def test_no_money_is_sent_without_a_calculation(self, client):
        """Pas de zéro déguisé en prix tant qu'aucun calcul n'a eu lieu."""
        body = client.get(
            f"/api/v1/bom/{VERSION}/children", params={"path": "V/A"}
        ).json()

        assert "unit_cost" not in body["items"][0]
        assert "own_contribution" not in body["items"][0]


class TestShareOnTheWire:
    @pytest.fixture
    def costed_client(self, bom):
        """Total 395 : A pèse 140 enfants compris, soit 35,4 %."""
        now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
        scenario = Scenario(
            id="scn", bom_version=VERSION, display_currency="EUR",
            labour_rate=Decimal("60.00"), parameters=(),
        )
        snapshot = PriceSnapshot(
            id="snp-1", taken_at=now, currency="EUR", source="mock",
            prices={"S": Decimal("10.000000")},
        )
        resolved = resolve_unit_prices(
            bom, FakeSourcingRepository().load(VERSION), snapshot, scenario
        )
        calculation = run_calculation(
            bom=bom, scenario=scenario, snapshot=snapshot, resolved=resolved,
            now=now, calculation_id="calc-1",
        )
        scenarios = FakeScenarioRepository()
        scenarios.create(scenario)
        calculations = FakeCalculationRepository()
        calculations.save(calculation)
        return TestClient(
            create_app(
                Repositories(
                    bom=FakeRepository(bom),
                    scenarios=scenarios,
                    calculations=calculations,
                )
            )
        )

    def test_the_share_travels_as_a_string_with_a_calculation(self, costed_client):
        body = costed_client.get(
            f"/api/v1/bom/{VERSION}/children",
            params={"path": "V", "calculation_id": "calc-1"},
        ).json()

        share = body["items"][0]["share_of_total_pct"]
        assert isinstance(share, str)
        assert share == "35.4"  # 140 / 395 × 100

    def test_no_share_is_sent_without_a_calculation(self, client):
        body = client.get(
            f"/api/v1/bom/{VERSION}/children", params={"path": "V"}
        ).json()

        assert "share_of_total_pct" not in body["items"][0]


class TestWhereUsedAndSearch:
    def test_where_used_lists_the_paths(self, client):
        body = client.get(
            f"/api/v1/bom/{VERSION}/where-used", params={"part_ref": "S"}
        ).json()

        assert {item["path"] for item in body["items"]} == {"V/A/S", "V/B/S"}
        assert body["total"] == 2

    def test_search_returns_paths_so_the_front_can_unfold(self, client):
        body = client.get(f"/api/v1/bom/{VERSION}/search", params={"q": "S"}).json()

        assert body["items"][0]["paths"]


class TestErrors:
    def test_an_unknown_path_is_a_named_404(self, client):
        response = client.get(
            f"/api/v1/bom/{VERSION}/children", params={"path": "V/S"}
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PATH_NOT_FOUND"

    def test_an_unknown_version_is_a_named_404(self, client):
        response = client.get("/api/v1/bom/nowhere/root")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOM_VERSION_NOT_FOUND"

    def test_a_version_that_failed_its_checks_refuses_to_be_read(self, bom):
        client = TestClient(
            create_app(Repositories(bom=FakeRepository(bom, validated=False)))
        )

        response = client.get(f"/api/v1/bom/{VERSION}/root")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "BOM_VERSION_NOT_VALIDATED"

    def test_the_path_parameter_is_required(self, client):
        response = client.get(f"/api/v1/bom/{VERSION}/children")

        assert response.status_code == 422


class TestVersions:
    """Le client dit sur quelle version il travaille : il faut donc qu'il
    puisse les connaître."""

    def test_lists_the_versions_with_their_counts(self, client):
        body = client.get("/api/v1/bom/versions").json()

        assert body == {
            "items": [
                {
                    "id": VERSION,
                    "label": "Losange de test",
                    "root_part_ref": "V",
                    "part_count": 4,
                    "edge_count": 4,
                    "validated_at": "2026-09-22T10:04:11+00:00",
                    "is_synthetic": True,
                }
            ]
        }

    def test_a_version_not_yet_validated_is_listed_as_such(self, bom):
        """Elle apparaît, pour que l'écran puisse dire pourquoi on ne peut pas
        l'ouvrir, plutôt que de la faire disparaître."""
        client = TestClient(
            create_app(Repositories(bom=FakeRepository(bom, validated=False)))
        )

        item = client.get("/api/v1/bom/versions").json()["items"][0]

        assert item["validated_at"] is None


class TestSearchTotalsAndBounds:
    def test_search_reports_its_totals(self, client):
        body = client.get(f"/api/v1/bom/{VERSION}/search", params={"q": "S"}).json()

        assert isinstance(body["total_parts"], int)
        assert isinstance(body["total_occurrences"], int)
        assert body["total_parts"] == 1
        assert body["total_occurrences"] == 2

    def test_max_paths_is_bounded(self, client):
        url = f"/api/v1/bom/{VERSION}/search"

        assert client.get(url, params={"q": "S", "max_paths": 201}).status_code == 422
        assert client.get(url, params={"q": "S", "max_paths": 0}).status_code == 422

        body = client.get(url, params={"q": "S", "max_paths": 1}).json()
        assert len(body["items"][0]["paths"]) == 1
        assert body["items"][0]["paths_truncated"] is True
