"""Import d'une variante de carrosserie, modèle 3D et fiche pièce, en HTTP.

Doubles en mémoire, vraie nomenclature du Multipla, vrais fichiers
`seeds/demo/*.glb`. Prix, densités et maquette sont synthétiques : ils ne
viennent d'aucun constructeur.
"""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from carcost.application.ports import Quote, StoredModel
from carcost.infrastructure.api.app import Repositories, create_app
from fakes import (
    FakeBodyModelRepository,
    FakeBomVersions,
    FakeCalculationRepository,
    FakeScenarioRepository,
    FakeSnapshotRepository,
    FakeSourcingRepository,
    FakeVariantWriter,
)
from real_multipla import (
    MULTIPLA,
    SEEDS,
    TAKEN_AT,
    mockup_bytes,
    multipla_bom,
    multipla_sourcing,
    multipla_summary,
    reference_snapshot,
)

DEMO = SEEDS / "demo"
RAW = {"content-type": "application/octet-stream"}
IMPORTS = f"/api/v1/bom/{MULTIPLA}/body-imports"
HOOD_DELTA = "-1.333147507383"


class PriceQuotes:
    """Une source de prix factice : chaque pièce demandée vaut son prix de référence."""

    def fetch(self, refs, currency):
        prices = reference_snapshot().prices
        return [Quote(ref, prices[ref], str(prices[ref])) for ref in refs if ref in prices]


class SlowWriter(FakeVariantWriter):
    def save_variant(self, variant):
        time.sleep(0.2)
        super().save_variant(variant)


def stack(*, writer=FakeVariantWriter, snapshots=True, modelled=True) -> Repositories:
    boms = FakeBomVersions((multipla_summary(), multipla_bom()))
    glb = mockup_bytes()
    models = FakeBodyModelRepository(
        *([StoredModel(MULTIPLA, glb, sha256(glb).hexdigest(), "generated")] if modelled else [])
    )
    return Repositories(
        bom=boms,
        sourcing=FakeSourcingRepository(multipla_sourcing()),
        snapshots=FakeSnapshotRepository(*([reference_snapshot()] if snapshots else [])),
        scenarios=FakeScenarioRepository(),
        calculations=FakeCalculationRepository(),
        models=models,
        variants=writer(boms, models, TAKEN_AT),
        prices=PriceQuotes(),
        clock=lambda: TAKEN_AT,
    )


@pytest.fixture
def repositories() -> Repositories:
    return stack()


@pytest.fixture
def client(repositories) -> TestClient:
    return TestClient(create_app(repositories))


def demo(name: str) -> bytes:
    return (DEMO / name).read_bytes()


def import_file(client, name: str, version: str = MULTIPLA):
    return client.post(f"/api/v1/bom/{version}/body-imports", content=demo(name), headers=RAW)


def calculate(client, scenario_id: str) -> dict:
    response = client.post("/api/v1/calculations", json={"scenario_id": scenario_id})
    assert response.status_code == 201, response.text
    return response.json()


def without_prices(repositories, *refs) -> None:
    snapshot = reference_snapshot()
    repositories.snapshots.snapshots[:] = [
        replace(snapshot, prices={r: p for r, p in snapshot.prices.items() if r not in refs})
    ]


def strings(value) -> bool:
    """Tout nombre sorti de l'API est une chaîne, jamais un flottant."""
    if isinstance(value, dict):
        return all(strings(v) for v in value.values())
    if isinstance(value, list):
        return all(strings(v) for v in value)
    return not isinstance(value, (int, float)) or isinstance(value, bool)


def change_of(body: dict, part_ref: str) -> dict:
    return next(c for c in body["changes"] if c["part_ref"] == part_ref)


def test_import_aluminium_hood_returns_201_with_string_amounts(client):
    response = import_file(client, "capot-alu.glb")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "CREATED"
    assert body["parent_version"] == MULTIPLA
    assert body["cost_status"] == "OK"
    assert body["cost"]["delta"] == {"amount": HOOD_DELTA, "currency": "EUR"}
    assert body["variant"]["id"].startswith(f"{MULTIPLA}+")
    [hood] = body["changes"]
    assert (hood["part_ref"], hood["kind"]) == ("CAR-HOOD-SHELL", "MODIFIED")
    assert (hood["mass_after_kg"], hood["mass_delta_kg"]) == ("3.852229", "-7.347771")
    assert body["material_mass_delta_kg"] == "-7.347771"
    assert (Decimal(hood["unit_cost_before"]), Decimal(hood["unit_cost_after"])) == (
        Decimal("23.8324016"), Decimal("22.499254092617"),
    )
    assert strings(body)
    assert isinstance(hood["mass_after_kg"], str) and isinstance(body["cost"]["delta"]["amount"], str)


def test_import_spoiler_returns_201(client):
    response = import_file(client, "aileron.glb")

    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(body["cost"]["delta"]["amount"]) == Decimal("6.5233862")
    assert Decimal(body["material_mass_delta_kg"]) == Decimal("3.15")
    spoiler = change_of(body, "BODY-SPOILER")
    assert (spoiler["kind"], spoiler["material_before"], spoiler["mass_before_kg"]) == ("NEW", None, None)
    assert (spoiler["unit_cost_before"], Decimal(spoiler["unit_cost_after"])) == (None, Decimal("6.5233862"))


def test_same_file_twice_returns_200_already_imported(client):
    first = import_file(client, "capot-alu.glb")
    second = import_file(client, "capot-alu.glb")

    assert second.status_code == 200, second.text
    assert second.json()["status"] == "ALREADY_IMPORTED"
    assert second.json()["message"] == "déjà importé"
    assert second.json()["variant"]["id"] == first.json()["variant"]["id"]
    assert second.json()["scenario_id"] is None
    assert second.json()["cost"]["delta"]["amount"] == first.json()["cost"]["delta"]["amount"]


def test_import_from_a_variant_is_named_after_the_file_and_hangs_off_the_origin(client):
    hood = import_file(client, "capot-alu.glb").json()["variant"]["id"]

    response = client.post(
        f"/api/v1/bom/{hood}/body-imports?name=aileron.glb", content=demo("aileron.glb"), headers=RAW,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["parent_version"] == MULTIPLA
    assert body["variant"]["label"].endswith(" — aileron")
    assert [c["part_ref"] for c in body["changes"]] == ["BODY-SPOILER"]


def test_reimported_mockup_returns_200_no_change(client):
    response = client.post(IMPORTS, content=mockup_bytes(), headers=RAW)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["message"], body["variant"], body["changes"]) == (
        "NO_CHANGE", "aucun changement", None, [],
    )
    assert body["cost"]["delta"]["amount"] == "0"


def test_surface_hood_returns_422_naming_the_object(client):
    response = import_file(client, "capot-surface.glb")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "BODY_IMPORT_REJECTED"
    fault = error["details"]["faults"][0]
    assert (fault["code"], fault["part_ref"]) == ("MESH_NOT_CLOSED", "CAR-HOOD-SHELL")
    assert fault["object"] and fault["message"]


def test_garbage_returns_422_invalid_model_file(client):
    response = client.post(IMPORTS, content=b"pas un glb", headers=RAW)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "BODY_IMPORT_REJECTED"
    assert [f["code"] for f in error["details"]["faults"]] == ["INVALID_MODEL_FILE"]


def test_import_on_version_without_model_returns_404():
    client = TestClient(create_app(stack(modelled=False)))

    response = import_file(client, "capot-alu.glb")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_import_on_unknown_version_returns_404(client):
    response = import_file(client, "capot-alu.glb", version="bom-inconnue")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BOM_VERSION_NOT_FOUND"


def test_import_on_incomplete_prices_returns_409_naming_the_parts(client, repositories):
    without_prices(repositories, "FIX-M8-20", "MAT-ALU-SHEET")

    response = import_file(client, "capot-alu.glb")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INCOMPLETE_CALCULATION"
    assert error["details"]["parts_without_price"] == ["FIX-M8-20", "MAT-ALU-SHEET"]
    assert error["details"]["snapshot_id"] == repositories.snapshots.latest(MULTIPLA).id
    assert "FIX-M8-20" in error["message"] and "MAT-ALU-SHEET" in error["message"]
    versions = client.get("/api/v1/bom/versions").json()["items"]
    assert [v["id"] for v in versions] == [MULTIPLA]


def test_body_changes_on_incomplete_prices_returns_409(client, repositories):
    variant = import_file(client, "capot-alu.glb").json()["variant"]["id"]
    without_prices(repositories, "FIX-M8-20", "MAT-ALU-SHEET")

    response = client.get(f"/api/v1/bom/{variant}/body-changes")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INCOMPLETE_CALCULATION"
    assert error["details"]["parts_without_price"] == ["FIX-M8-20", "MAT-ALU-SHEET"]


def test_two_simultaneous_imports_create_one_scenario(repositories):
    slow = stack(writer=SlowWriter)
    client = TestClient(create_app(slow))
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(import_file(client, "aileron.glb").status_code))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [200, 201]
    assert len(slow.scenarios.scenarios) == 1


def test_model_route_serves_the_glb(client):
    response = client.get(f"/api/v1/bom/{MULTIPLA}/model")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("model/gltf-binary")
    assert response.content == mockup_bytes()
    variant = import_file(client, "capot-alu.glb").json()["variant"]["id"]
    assert client.get(f"/api/v1/bom/{variant}/model").content == demo("capot-alu.glb")


def test_model_route_without_model_or_version_returns_404():
    client = TestClient(create_app(stack(modelled=False)))

    for version in (MULTIPLA, "bom-inconnue"):
        response = client.get(f"/api/v1/bom/{version}/model")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_body_changes_after_import(client):
    variant = import_file(client, "capot-alu.glb").json()["variant"]["id"]

    body = client.get(f"/api/v1/bom/{variant}/body-changes").json()

    assert body["version"] == variant
    assert body["parent_version"] == MULTIPLA
    assert body["cost"]["delta"]["amount"] == HOOD_DELTA
    assert body["cost_status"] == "OK"
    assert body["material_mass_delta_kg"] == "-7.347771"
    assert [c["part_ref"] for c in body["changes"]] == ["CAR-HOOD-SHELL"]

    origin = client.get(f"/api/v1/bom/{MULTIPLA}/body-changes").json()
    assert (origin["parent_version"], origin["changes"], origin["cost"]) == (None, [], None)
    assert client.get("/api/v1/bom/bom-inconnue/body-changes").status_code == 404


def test_versions_expose_parent_version_id(client):
    variant = import_file(client, "capot-alu.glb").json()["variant"]["id"]

    items = {v["id"]: v for v in client.get("/api/v1/bom/versions").json()["items"]}

    assert items[variant]["parent_version_id"] == MULTIPLA
    assert "parent_version_id" not in items[MULTIPLA]


def test_import_aluminium_body_returns_exact_euros_and_masses(client):
    response = import_file(client, "carrosserie-alu.glb")

    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(body["cost"]["delta"]["amount"]) == Decimal("-8.332166788091")
    assert Decimal(body["cost"]["total_after"]["amount"]) == Decimal("13277.328834381909")
    assert Decimal(body["material_mass_delta_kg"]) == Decimal("-45.923567")
    assert len(body["changes"]) == 5
    expected = {
        "CAR-DOOR-SHELL-FRONT": ("24.6021942", "23.483303222933"),
        "CAR-DOOR-SHELL-REAR": ("22.2998798", "21.276214273426"),
        "CAR-PANEL-ROOF": ("25.1858732", "23.709888983464"),
        "CAR-TAILGATE-SHELL": ("24.3300872", "23.09216514311"),
        "CAR-HOOD-SHELL": ("23.8324016", "22.499254092617"),
    }
    for ref, (before, after) in expected.items():
        change = change_of(body, ref)
        assert (Decimal(change["unit_cost_before"]), Decimal(change["unit_cost_after"])) == (
            Decimal(before), Decimal(after),
        )
    front = change_of(body, "CAR-DOOR-SHELL-FRONT")
    assert Decimal(front["cumulative_quantity"]) == 2
    assert (Decimal(front["mass_before_kg"]), front["mass_after_kg"]) == (Decimal("9.4"), "3.233121")
    assert strings(body)


def test_spoiler_part_card_proves_it_is_in_the_bom(client):
    body = import_file(client, "aileron.glb").json()
    variant = body["variant"]["id"]
    calculation = calculate(client, body["scenario_id"])

    children = client.get(
        f"/api/v1/bom/{variant}/children", params={"path": "VEH-MULTIPLA-16V/CAR-ASSY", "limit": 500}
    ).json()["items"]
    assert "BODY-SPOILER" in [item["part_ref"] for item in children]
    used = client.get(f"/api/v1/bom/{variant}/where-used", params={"part_ref": "BODY-SPOILER"}).json()
    assert [o["path"] for o in used["items"]] == ["VEH-MULTIPLA-16V/CAR-ASSY/BODY-SPOILER"]

    card = client.get(
        f"/api/v1/bom/{variant}/parts/BODY-SPOILER", params={"calculation_id": calculation["id"]}
    ).json()
    assert card["material_ref"] == "MAT-ABS-GRANULE"
    assert Decimal(card["material_quantity_kg"]) == Decimal("3.15")
    fixings = {c["part_ref"]: c for c in card["composition"]}
    assert Decimal(fixings["FIX-M8-20"]["quantity"]) == 4
    assert Decimal(card["cumulative_quantity"]) == 1
    assert Decimal(card["unit_cost"]["amount"]) == Decimal("6.5233862")
    assert Decimal(card["own_contribution"]["amount"]) == 0
    assert card["price_status"] == "OK"
    assert all(isinstance(card[k], str) for k in ("material_quantity_kg", "mass_kg", "cumulative_quantity"))
    assert all(isinstance(m["quantity"], str) for m in card["composition"])


def test_aluminium_door_part_card(client):
    body = import_file(client, "carrosserie-alu.glb").json()
    variant = body["variant"]["id"]
    calculation = calculate(client, body["scenario_id"])

    card = client.get(
        f"/api/v1/bom/{variant}/parts/CAR-DOOR-SHELL-FRONT", params={"calculation_id": calculation["id"]}
    ).json()

    assert card["material_ref"] == "MAT-ALU-SHEET"
    assert Decimal(card["material_quantity_kg"]) == Decimal("3.233121")
    assert Decimal(card["cumulative_quantity"]) == 2
    assert Decimal(card["unit_cost"]["amount"]) == Decimal("23.483303222933")
    changes = client.get(f"/api/v1/bom/{variant}/body-changes").json()
    door = change_of(changes, "CAR-DOOR-SHELL-FRONT")
    assert (Decimal(door["mass_before_kg"]), door["mass_after_kg"]) == (Decimal("9.4"), "3.233121")
    assert (Decimal(door["unit_cost_before"]), Decimal(door["unit_cost_after"])) == (
        Decimal("24.6021942"), Decimal("23.483303222933"),
    )


def test_part_card_without_calculation_has_no_cost_keys(client):
    card = client.get(f"/api/v1/bom/{MULTIPLA}/parts/CAR-HOOD-SHELL").json()

    assert card["material_ref"] == "MAT-STEEL-SHEET"
    assert Decimal(card["mass_kg"]) == Decimal("11.2")
    assert Decimal(card["material_quantity_kg"]) == Decimal("11.2")
    assert card["composition"][0]["part_ref"] == "MAT-STEEL-SHEET"
    for key in ("unit_cost", "own_unit_cost", "cumulative_quantity", "own_contribution", "price_status"):
        assert key not in card
    unknown = client.get(f"/api/v1/bom/{MULTIPLA}/parts/CAR-HOOD-SHELL", params={"calculation_id": "calc-inconnu"})
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "CALCULATION_NOT_FOUND"


def test_variant_calculation_uses_the_origin_snapshot(client):
    scenario_id = import_file(client, "capot-alu.glb").json()["scenario_id"]

    calculation = calculate(client, scenario_id)

    assert calculation["price_snapshot"]["id"] == reference_snapshot().id
    assert calculation["status"] != "INCOMPLETE"


def test_freezing_prices_on_a_variant_targets_the_origin(client, repositories):
    variant = import_file(client, "aileron.glb").json()["variant"]["id"]

    response = client.post("/api/v1/price-snapshots", json={"bom_version": variant})

    assert response.status_code == 201, response.text
    assert response.json()["bom_version"] == MULTIPLA
    assert repositories.snapshots.latest(MULTIPLA).bom_version == MULTIPLA


def test_a_variant_lists_the_origin_price_snapshots(client):
    variant = import_file(client, "aileron.glb").json()["variant"]["id"]

    response = client.get("/api/v1/price-snapshots", params={"bom_version": variant})

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [reference_snapshot().id]
