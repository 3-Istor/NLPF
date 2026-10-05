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

    def test_the_serialised_systems_sum_exactly_to_the_serialised_total(self, client):
        """Pas « une fois désérialisés » : les chaînes elles-mêmes.

        Arrondir chaque montant à la sérialisation casse l'addition — dix
        montants arrondis ne somment pas au total arrondi. Le défaut n'est
        apparu qu'en exécutant le vrai calcul sur les 474 pièces, avec un écart
        de deux millionièmes d'euro.
        """
        scenario_id = make_scenario(client)
        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        total = Decimal(body["total_cost"]["amount"])
        systems = sum(Decimal(s["cost"]["amount"]) for s in body["systems"])

        assert systems - total == Decimal(0)

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


class TestCarbon:
    """S est la seule pièce à porter du CO2 dans cette nomenclature : sa
    matière est nulle par défaut, seul son transport compte (usine par défaut
    de `FakeSourcingRepository`, 0.021 kg CO2e/kg, pour 1 kg et 23 vis
    cumulées) : 0.021 × 1 × 23 = 0.483.
    """

    def test_total_co2_is_the_hand_computed_value(self, client):
        scenario_id = make_scenario(client)

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert body["total_co2"]["kg_co2e"] == "0.483000"

    def test_the_system_co2_sums_to_the_total(self, client):
        scenario_id = make_scenario(client)

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert sum(
            Decimal(system["co2"]["kg_co2e"]) for system in body["systems"]
        ) == Decimal(body["total_co2"]["kg_co2e"])

    def test_top_co2_contributors_names_the_only_emitter(self, client):
        scenario_id = make_scenario(client)

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert body["top_co2_contributors"][0]["part_ref"] == "S"
        assert (
            body["top_co2_contributors"][0]["own_co2_contribution"]["kg_co2e"]
            == "0.483000"
        )

    def test_the_aggregated_view_exposes_each_line_s_co2(self, client):
        scenario_id = make_scenario(client)
        calculation = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        body = client.get(
            f"/api/v1/calculations/{calculation['id']}/aggregated",
            params={"limit": 500},
        ).json()

        by_ref = {item["part_ref"]: item for item in body["items"]}
        assert by_ref["S"]["own_co2_contribution"]["kg_co2e"] == "0.483000"
        assert Decimal(by_ref["V"]["own_co2_contribution"]["kg_co2e"]) == Decimal(0)

    def test_a_complete_calculation_names_no_part_without_co2(self, client):
        scenario_id = make_scenario(client)

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert body["parts_without_co2"] == []

    def test_a_forced_price_leaves_the_cost_complete_and_the_co2_unknown(
        self, client
    ):
        """Le prix forcé ne retient aucune usine : le transport de S est
        inconnu. Le total CO2 ne doit pas se lire comme celui du véhicule."""
        scenario_id = make_scenario(client)
        response = client.put(
            f"/api/v1/scenarios/{scenario_id}/parameters/S",
            json={
                "scope": "part",
                "price_override": "9.99",
                "price_override_justification": "devis du 2026-09-20",
            },
        )
        assert response.status_code in (200, 201), response.text

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert body["parts_without_price"] == []
        assert body["parts_without_co2"] == ["S"]
        assert body["top_co2_contributors"] == [] or all(
            item["part_ref"] != "S" for item in body["top_co2_contributors"]
        )


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

    def test_a_labour_time_set_on_an_assembly_changes_the_total(self, client):
        """A passe de 30 à 90 min, deux A par véhicule : 120 € de plus.
        Accepté, marqué obsolète, puis recalculé à l'identique, ce paramètre
        ferait croire à l'utilisateur qu'il a changé quelque chose."""
        scenario_id = make_scenario(client)
        client.put(
            f"/api/v1/scenarios/{scenario_id}/parameters/A",
            json={"scope": "part", "labour_minutes": "90"},
        )

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert body["total_cost"]["amount"] == "515.000000"

    def test_a_labour_rate_set_on_an_assembly_changes_the_total(self, client):
        """A passe de 60 à 120 €/h, deux A de 30 min : 60 € de plus. Le
        calcul précédent devient obsolète : le taux entre dans l'empreinte."""
        scenario_id = make_scenario(client)
        client.post("/api/v1/calculations", json={"scenario_id": scenario_id})
        client.put(
            f"/api/v1/scenarios/{scenario_id}/parameters/A",
            json={"scope": "part", "labour_rate": "120"},
        )
        assert (
            client.get(f"/api/v1/scenarios/{scenario_id}").json()["calculation_state"]
            != "UP_TO_DATE"
        )

        body = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()

        assert body["total_cost"]["amount"] == "455.000000"


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


class TestCostedTreeLines:
    """Ce que l'arbre affiche une fois qu'un calcul existe."""

    def calculate(self, client) -> tuple[str, str]:
        scenario_id = make_scenario(client)
        calculation = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()
        return scenario_id, calculation["id"]

    def children(self, client, path, calculation_id):
        return client.get(
            f"/api/v1/bom/{VERSION}/children",
            params={"path": path, "calculation_id": calculation_id},
        ).json()["items"]

    def test_a_line_shows_what_this_occurrence_weighs(self, client):
        """Sous A il y a 8 vis à 10 € : 80 €. Sous B, 15 vis : 150 €.
        Même pièce, deux lignes, deux montants."""
        _, calculation_id = self.calculate(client)

        under_a = self.children(client, "V/A", calculation_id)[0]
        under_b = self.children(client, "V/B", calculation_id)[0]

        assert under_a["rolled_up_contribution"]["amount"] == "80.000000"
        assert under_b["rolled_up_contribution"]["amount"] == "150.000000"

    def test_on_an_assembly_the_two_montants_differ(self, client):
        """A : 60 € de main-d'œuvre en propre, 140 € enfants compris.
        Les additionner reviendrait à compter la vis deux fois."""
        _, calculation_id = self.calculate(client)

        assembly = next(
            item
            for item in self.children(client, "V", calculation_id)
            if item["part_ref"] == "A"
        )

        assert assembly["own_contribution"]["amount"] == "60.000000"
        assert assembly["rolled_up_contribution"]["amount"] == "140.000000"

    def test_a_modified_part_is_marked_and_so_is_its_way_up(self, client):
        """Sans la remontée, un réglage posé sur une vis est introuvable."""
        scenario_id, _ = self.calculate(client)
        client.put(
            f"/api/v1/scenarios/{scenario_id}/parameters/S",
            json={"scope": "part", "supplier_id": "SUP-DE"},
        )
        calculation_id = client.post(
            "/api/v1/calculations", json={"scenario_id": scenario_id}
        ).json()["id"]

        screw = self.children(client, "V/A", calculation_id)[0]
        assembly = next(
            item
            for item in self.children(client, "V", calculation_id)
            if item["part_ref"] == "A"
        )

        assert screw["is_modified"] is True
        assert screw["has_modified_descendant"] is False
        assert assembly["is_modified"] is False
        assert assembly["has_modified_descendant"] is True

    def test_nothing_is_marked_on_an_untouched_scenario(self, client):
        _, calculation_id = self.calculate(client)

        assert all(
            item["is_modified"] is False and item["has_modified_descendant"] is False
            for item in self.children(client, "V", calculation_id)
        )


class TestPartDetail:
    """Le panneau de saisie se construit sur cette réponse."""

    def test_a_purchased_part_offers_its_suppliers_and_their_plants(self, client):
        body = client.get(f"/api/v1/bom/{VERSION}/parts/S").json()

        assert body["valuation_mode"] == "purchased"
        assert [s["supplier_id"] for s in body["suppliers"]] == ["SUP-IT", "SUP-DE"]
        assert len(body["suppliers"][0]["plants"]) == 2

    def test_an_assembly_has_no_suppliers_key_at_all(self, client):
        """Absente, pas vide. Une liste vide inviterait l'écran à afficher un
        sélecteur sans options ; l'absence lui dit qu'il n'y a rien à choisir."""
        body = client.get(f"/api/v1/bom/{VERSION}/parts/A").json()

        assert body["valuation_mode"] == "manufactured"
        assert "suppliers" not in body

    def test_an_unknown_reference_is_a_named_404(self, client):
        response = client.get(f"/api/v1/bom/{VERSION}/parts/NOWHERE")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PATH_NOT_FOUND"


def calculate(client) -> str:
    scenario_id = make_scenario(client)
    return client.post(
        "/api/v1/calculations", json={"scenario_id": scenario_id}
    ).json()["id"]


class TestExplain:
    """docs/api.md §4.4. À la main : S vaut 10 × 1 × 1 = 10 ; A vaut
    4 × 10 + 30 min à 60 €/h = 70."""

    def explain(self, client, path):
        return client.get(
            f"/api/v1/calculations/{calculate(client)}/explain", params={"path": path}
        )

    def test_a_purchased_line_shows_its_three_factors(self, client):
        body = self.explain(client, "V/A/S").json()

        breakdown = body["unit_cost_breakdown"]
        assert breakdown["kind"] == "catalogue"
        assert breakdown["reference_price"] == {"amount": "10.000000", "currency": "EUR"}
        assert breakdown["supplier"]["supplier_id"] == "SUP-IT"
        assert breakdown["plant"]["plant_id"] == "PLT-IT"
        assert breakdown["formula"] == "10.000000 × 1.000000 × 1.000000"
        assert breakdown["unit_cost"]["amount"] == "10.000000"
        assert breakdown["reproduced"] is True

    def test_both_quantities_travel_as_strings(self, client):
        body = self.explain(client, "V/A/S").json()

        assert body["quantity"] == {
            "on_path": "8.000000",
            "cumulative_in_vehicle": "23.000000",
            "unit": "pce",
        }

    def test_an_assembly_shows_children_and_labour_and_no_price(self, client):
        body = self.explain(client, "V/A").json()

        breakdown = body["unit_cost_breakdown"]
        assert breakdown["kind"] == "assembly"
        assert breakdown["children"] == [
            {
                "part_ref": "S",
                "quantity": "4.000000",
                "unit_cost": {"amount": "10.000000", "currency": "EUR"},
                "contribution": {"amount": "40.000000", "currency": "EUR"},
            }
        ]
        assert breakdown["labour"]["amount"]["amount"] == "30.000000"
        assert breakdown["unit_cost"]["amount"] == "70.000000"
        assert "reference_price" not in breakdown

    def test_it_names_the_snapshot_the_price_came_from(self, client):
        body = self.explain(client, "V/A/S").json()

        assert body["price_source"]["snapshot_id"] == "snp-1"
        assert body["price_source"]["status"] == "OK"

    def test_an_unknown_path_is_a_named_404(self, client):
        response = self.explain(client, "V/S")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PATH_NOT_FOUND"


class TestIssues:
    """docs/api.md §4.5 : la liste cliquable exigée par le mode de panne P3."""

    def test_a_clean_calculation_has_no_issue(self, client):
        body = client.get(f"/api/v1/calculations/{calculate(client)}/issues").json()

        assert body["items"] == []
        assert body["total"] == 0

    def test_a_part_without_price_is_listed_with_a_path_to_unfold(self, bom):
        without_price = Repositories(
            bom=FakeBomRepository(bom, version=VERSION),
            sourcing=FakeSourcingRepository(),
            snapshots=FakeSnapshotRepository(
                PriceSnapshot(
                    id="snp-1", taken_at=NOW, currency="EUR", source="mock",
                    prices={}, missing_refs=frozenset({"S"}),
                )
            ),
            scenarios=FakeScenarioRepository(),
            calculations=FakeCalculationRepository(),
            clock=lambda: NOW,
        )
        client = TestClient(create_app(without_price))

        body = client.get(f"/api/v1/calculations/{calculate(client)}/issues").json()

        assert body["items"] == [
            {
                "kind": "MISSING_PRICE",
                "part_ref": "S",
                "label": "S",
                "system": "TST",
                "path": "V/A/S",
                "cumulative_quantity": "23.000000",
                "occurrence_count": 2,
            }
        ]
