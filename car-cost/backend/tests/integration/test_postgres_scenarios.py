"""NLPF-42 sur PostgreSQL : transactions annulées, aucune donnée de test conservée."""

import os
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from carcost.application import manage_scenarios
from carcost.application.ports import ScenarioNotFound
from carcost.application.scenario import Scenario, ScenarioParameter
from carcost.infrastructure.api.app import Repositories, create_app
from carcost.infrastructure.postgres.bom import PostgresBomRepository
from carcost.infrastructure.postgres.scenarios import PostgresScenarioRepository
from carcost.infrastructure.postgres.sourcing import PostgresSourcingRepository
from fakes import FakeCalculationRepository, FakeSnapshotRepository

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")
VERSION = os.environ.get("CARCOST_BOM_VERSION", "bom-multipla-2026-09-22")


class Held:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_):
        return False


@pytest.fixture
def connection():
    import psycopg

    try:
        connection = psycopg.connect(DSN, connect_timeout=3)
    except psycopg.OperationalError as unreachable:
        pytest.skip(f"Postgres injoignable : {unreachable}")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def held(repository, connection):
    repository._connect = lambda: Held(connection)
    return repository


@pytest.fixture
def repositories(connection):
    return Repositories(
        bom=held(PostgresBomRepository(DSN), connection),
        sourcing=held(PostgresSourcingRepository(DSN), connection),
        scenarios=held(PostgresScenarioRepository(DSN), connection),
        snapshots=FakeSnapshotRepository(), calculations=FakeCalculationRepository(),
    )


@pytest.fixture
def original(repositories):
    from carcost.application.browse_bom import where_used

    bom = repositories.bom.load(VERSION)
    sourcing = repositories.sourcing.load(VERSION)
    # Une pièce partagée réelle : des occurrences distinctes doivent survivre
    # à l'aller-retour, en plus du réglage global de cette même référence.
    ref, occurrences = next(
        (ref, page.items)
        for ref, part in bom.parts.items() if part.is_purchased
        if (page := where_used(bom, ref)).total >= 2
    )
    offer = sourcing.default_offer(ref)
    plant = sourcing.default_plant(offer.supplier_id)
    manufactured = next(ref for ref, part in bom.parts.items() if not part.is_purchased)
    return Scenario(
        id=f"scn-test-{uuid.uuid4().hex}", bom_version=VERSION,
        name="Essai été — données synthétiques", display_currency="EUR",
        labour_rate=Decimal("42.123456"), active_rules=frozenset(),
        parameters=(
            ScenarioParameter(
                ref, supplier_id=offer.supplier_id, plant_id=plant.plant_id,
                purchase_currency="USD", price_override=Decimal("1.123456"),
                price_override_justification="Offre synthétique",
            ),
            ScenarioParameter(ref, "path", occurrences[0].path, purchase_currency="RUB"),
            ScenarioParameter(ref, "path", occurrences[1].path, purchase_currency="EUR"),
            ScenarioParameter(manufactured, labour_minutes=Decimal("12.3456")),
        ),
    )


def test_full_round_trip_in_postgres(repositories, original, connection):
    manage_scenarios.create_scenario(
        original, repositories.bom, repositories.scenarios, repositories.sourcing,
    )
    # Un nouvel adaptateur relit les lignes, sans objet en mémoire partagé.
    reader = held(PostgresScenarioRepository(DSN), connection)
    assert reader.get(original.id) == original


def test_scenarios_are_listed_newest_first_in_postgres(repositories, original):
    first = replace(original, id="scn-test-list-a", name="Premier")
    second = replace(original, id="scn-test-list-b", name="Deuxième")
    repositories.scenarios.create(first)
    repositories.scenarios.create(second)

    listed = [
        scenario
        for scenario in repositories.scenarios.list_all()
        if scenario.id in {first.id, second.id}
    ]

    assert listed == [second, first]


def test_duplicate_and_parameter_changes_are_independent_in_postgres(repositories, original):
    manage_scenarios.create_scenario(
        original, repositories.bom, repositories.scenarios, repositories.sourcing,
    )
    copied = manage_scenarios.duplicate_scenario(
        original.id, name="Alternative", scenario_id=f"scn-test-{uuid.uuid4().hex}",
        boms=repositories.bom, scenarios=repositories.scenarios, sourcing=repositories.sourcing,
    )
    assert copied == replace(original, id=copied.id, name="Alternative")
    global_parameter = next(p for p in original.parameters if p.purchase_currency == "USD")
    changed = replace(global_parameter, purchase_currency="EUR", price_override=Decimal("2.654321"))
    parameter_id = manage_scenarios.put_parameter(
        copied.id, changed, repositories.bom, repositories.scenarios, repositories.sourcing,
    )
    same_id = manage_scenarios.put_parameter(
        copied.id, changed, repositories.bom, repositories.scenarios, repositories.sourcing,
    )
    assert same_id == parameter_id
    assert repositories.scenarios.get(copied.id).parameter_for(changed.part_ref) == changed
    assert repositories.scenarios.get(original.id) == original
    repositories.scenarios.delete_parameter(copied.id, parameter_id)
    assert repositories.scenarios.get(copied.id).parameter_for(changed.part_ref) is None
    assert repositories.scenarios.get(original.id) == original


def test_deleting_scenario_cascades_parameters_and_calculations(
    repositories, original, connection,
):
    manage_scenarios.create_scenario(
        original, repositories.bom, repositories.scenarios, repositories.sourcing,
    )
    calculation_id = f"cal-test-{uuid.uuid4().hex}"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO calculation
                (id, scenario_id, bom_version_id, price_snapshot_id,
                 rules_version, engine_version, active_rules, status,
                 display_currency, total_cost, total_co2, input_digest,
                 started_at, finished_at)
            VALUES
                (%s, %s, %s, NULL, 'test-rules', 'test-engine', '{}',
                 'OK', 'EUR', 1, NULL, 'test-digest', now(), now())
            """,
            (calculation_id, original.id, VERSION),
        )

    repositories.scenarios.delete(original.id)

    with pytest.raises(ScenarioNotFound):
        repositories.scenarios.get(original.id)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM scenario_parameter WHERE scenario_id = %s",
            (original.id,),
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "SELECT count(*) FROM calculation WHERE id = %s", (calculation_id,),
        )
        assert cursor.fetchone()[0] == 0


def test_unknown_part_via_api_does_not_persist_in_postgres(repositories, original, connection):
    manage_scenarios.create_scenario(
        original, repositories.bom, repositories.scenarios, repositories.sourcing,
    )
    client = TestClient(create_app(repositories))
    response = client.put(
        f"/api/v1/scenarios/{original.id}/parameters/UNKNOWN-PART",
        json={"purchase_currency": "USD"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PARAMETER_NOT_APPLICABLE"
    assert "UNKNOWN-PART" in response.json()["error"]["message"]
    assert repositories.scenarios.get(original.id) == original
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM scenario_parameter WHERE scenario_id = %s AND part_ref = %s",
            (original.id, "UNKNOWN-PART"),
        )
        assert cursor.fetchone()[0] == 0


def test_create_rolls_back_header_and_parameters_on_failure(connection, original):
    """Vérifie l'atomicité de l'adaptateur même si l'appelant a omis la validation."""
    import psycopg

    class Transactional(Held):
        def __enter__(self):
            self.transaction = self.connection.transaction()
            self.transaction.__enter__()
            return self.connection

        def __exit__(self, *args):
            return self.transaction.__exit__(*args)

    repository = PostgresScenarioRepository(DSN)
    repository._connect = lambda: Transactional(connection)
    invalid = replace(original, parameters=original.parameters + (
        ScenarioParameter("ZZZ-TEST", supplier_id="UNKNOWN-SUPPLIER"),
    ))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repository.create(invalid)
    with pytest.raises(ScenarioNotFound):
        repository.get(original.id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM scenario_parameter WHERE scenario_id = %s", (original.id,))
        assert cursor.fetchone()[0] == 0
