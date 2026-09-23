"""Les routes de lecture du graphe, contre le contrat de docs/api.md."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from carcost.application.ports import BomVersionNotFound, BomVersionNotValidated
from carcost.domain.bom import Bom, Edge
from carcost.infrastructure.api.app import Repositories, create_app
from factories import manufactured, purchased

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
