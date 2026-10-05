"""ADR-0014 sur PostgreSQL : l'adaptateur des snapshots de calcul.

Transaction tenue puis annulée : un snapshot de calcul ne se supprime pas,
un snapshot de test resterait sinon en base. Le snapshot de prix est créé dans
la transaction : la base de CI n'en contient aucun.
"""

import os
import uuid
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from carcost.application.freeze_calculation import (
    derive_scenario, freeze_scenario, rename_snapshot,
)
from carcost.application.ports import CalculationSnapshotNotFound, SnapshotNameTaken
from carcost.application.price_resolution import resolve_unit_prices
from carcost.application.run_calculation import run_calculation
from carcost.application.scenario import Scenario, ScenarioParameter
from carcost.domain.prices import PriceSnapshot
from carcost.infrastructure.postgres.bom import PostgresBomRepository
from carcost.infrastructure.postgres.calculation_snapshots import (
    PostgresCalculationSnapshotRepository,
)
from carcost.infrastructure.postgres.calculations import PostgresCalculationRepository
from carcost.infrastructure.postgres.scenarios import PostgresScenarioRepository
from carcost.infrastructure.postgres.snapshots import PostgresPriceSnapshotRepository
from carcost.infrastructure.postgres.sourcing import PostgresSourcingRepository

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")
VERSION = os.environ.get("CARCOST_BOM_VERSION", "bom-multipla-2026-09-22")
NOW = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)


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


class World:
    """Les dépôts Postgres tenus sur une connexion, un scénario et un prix."""

    def __init__(self, connection):
        self.bom = held(PostgresBomRepository(DSN), connection)
        self.sourcing = held(PostgresSourcingRepository(DSN), connection)
        self.scenarios = held(PostgresScenarioRepository(DSN), connection)
        self.calculations = held(PostgresCalculationRepository(DSN), connection)
        self.snapshots_repo = held(PostgresCalculationSnapshotRepository(DSN), connection)

        bom = self.bom.load(VERSION)
        sourcing = self.sourcing.load(VERSION)
        purchased = sorted(ref for ref, part in bom.parts.items() if part.is_purchased)
        manufactured = next(
            ref for ref, part in bom.parts.items() if not part.is_purchased
        )
        self.price_snapshot = PriceSnapshot(
            id=f"snp-test-{uuid.uuid4().hex[:12]}", taken_at=NOW - timedelta(minutes=5),
            currency="EUR", source="mock",
            prices={ref: Decimal("1.5") for ref in purchased},
        )
        held(PostgresPriceSnapshotRepository(DSN), connection).save(self.price_snapshot)

        ref = purchased[0]
        offer = sourcing.default_offer(ref)
        plant = sourcing.default_plant(offer.supplier_id)
        self.scenario = Scenario(
            id=f"scn-test-{uuid.uuid4().hex[:12]}", bom_version=VERSION,
            name="Étude de gel — données synthétiques", display_currency="EUR",
            labour_rate=Decimal("42.123456"), active_rules=frozenset({"labour"}),
            parameters=(
                ScenarioParameter(
                    ref, supplier_id=offer.supplier_id, plant_id=plant.plant_id,
                    purchase_currency="USD",
                ),
                ScenarioParameter(ref, "path", ref, purchase_currency="RUB"),
                ScenarioParameter(
                manufactured, labour_minutes=Decimal("12.3456"),
                labour_rate=Decimal("77.123456"),
            ),
            ),
        )
        self.scenarios.create(self.scenario)
        self.sequence = 0

    def calculate(self, scenario: Scenario):
        bom = self.bom.load(scenario.bom_version)
        resolved = resolve_unit_prices(
            bom, self.sourcing.load(scenario.bom_version), self.price_snapshot, scenario,
        )
        calculation = run_calculation(
            bom=bom, scenario=scenario, snapshot=self.price_snapshot,
            resolved=resolved, now=NOW,
            calculation_id=f"calc-test-{uuid.uuid4().hex[:12]}",
        )
        self.calculations.save(calculation)
        return calculation

    def freeze(self, name: str, *, now: datetime = NOW):
        self.sequence += 1
        return freeze_scenario(
            self.scenario.id, name, scenarios=self.scenarios, boms=self.bom,
            snapshots_repo=self.snapshots_repo, calculate=self.calculate,
            snapshot_id=f"csn-test-{uuid.uuid4().hex[:12]}", now=now,
        )


@pytest.fixture
def world(connection):
    return World(connection)


def test_a_frozen_snapshot_reads_back_identically(world, connection):
    frozen = world.freeze("Référence T3")

    # Un nouvel adaptateur relit les lignes, sans objet en mémoire partagé.
    reader = held(PostgresCalculationSnapshotRepository(DSN), connection)
    assert reader.get(frozen.id) == frozen
    assert len(frozen.parameters) == 3
    assert {p.scope for p in frozen.parameters} == {"part", "path"}


def test_a_frozen_snapshot_carries_the_references_of_its_calculation(world, connection):
    frozen = world.freeze("Références du calcul")

    row = connection.execute(
        "SELECT bom_version_id, scenario_id, price_snapshot_id"
        " FROM calculation WHERE id = %s",
        (frozen.calculation_id,),
    ).fetchone()
    read = world.snapshots_repo.get(frozen.id)
    assert (read.bom_version, read.scenario_id, read.price_snapshot_id) == row
    assert read.price_snapshot_id == world.price_snapshot.id


def test_the_list_is_newest_first_and_per_version(world):
    first = world.freeze("Premier gel", now=NOW)
    second = world.freeze("Second gel", now=NOW + timedelta(hours=1))

    listed = world.snapshots_repo.list_for(VERSION)

    assert [s.id for s in listed if s.id in {first.id, second.id}] == [second.id, first.id]
    assert world.snapshots_repo.list_for("bom-inexistante") == ()


def test_renaming_is_traced(world):
    frozen = world.freeze("Brouillon")

    renamed = rename_snapshot(
        frozen.id, "Gel retenu", snapshots_repo=world.snapshots_repo,
        now=NOW + timedelta(hours=1),
    )

    assert renamed == replace(frozen, name="Gel retenu")
    assert world.snapshots_repo.name_history(frozen.id) == (
        ("Brouillon", NOW), ("Gel retenu", NOW + timedelta(hours=1)),
    )


def test_a_taken_name_is_a_named_error(world):
    first = world.freeze("Référence T3")
    # Le cas d'usage refuse avant l'écriture ; on s'adresse donc à l'adaptateur,
    # là où seule la contrainte unique protège (deux requêtes concurrentes).
    twin = replace(
        first, id=f"csn-test-{uuid.uuid4().hex[:12]}", name="reference t3",
        calculation_id=world.calculate(world.scenario).id,
    )

    with pytest.raises(SnapshotNameTaken) as refused:
        world.snapshots_repo.save(twin)
    assert refused.value.existing_id == first.id

    # Un renommage vers un nom pris est refusé de la même façon.
    other = world.freeze("Autre gel")
    with pytest.raises(SnapshotNameTaken):
        world.snapshots_repo.rename(other.id, "RÉFÉRENCE T3", NOW)
    assert world.snapshots_repo.get(other.id).name == "Autre gel"
    assert len(world.snapshots_repo.name_history(other.id)) == 1


def test_changing_the_scenario_after_freezing_does_not_change_the_snapshot(world):
    frozen = world.freeze("Gel avant retouche")

    world.scenarios.put_parameter(
        world.scenario.id,
        replace(world.scenario.parameters[0], purchase_currency="EUR"),
    )

    assert world.scenarios.get(world.scenario.id).parameters != frozen.parameters
    assert world.snapshots_repo.get(frozen.id).parameters == frozen.parameters


def test_an_unknown_snapshot_is_reported(world):
    with pytest.raises(CalculationSnapshotNotFound):
        world.snapshots_repo.get("csn-inconnu")
    with pytest.raises(CalculationSnapshotNotFound):
        world.snapshots_repo.rename("csn-inconnu", "Nom", NOW)
    with pytest.raises(CalculationSnapshotNotFound):
        world.snapshots_repo.name_history("csn-inconnu")


def test_for_scenario_lists_the_snapshots_carried(world):
    first = world.freeze("Premier porté", now=NOW)
    second = world.freeze("Second porté", now=NOW + timedelta(hours=1))

    carried = world.snapshots_repo.for_scenario(world.scenario.id)

    assert [s.id for s in carried] == [second.id, first.id]
    assert world.snapshots_repo.for_scenario("scn-sans-gel") == ()


def test_a_derived_scenario_and_its_freeze_keep_the_origin_in_postgres(
    world, connection,
):
    origin = world.freeze("Gel d'origine")
    derived = replace(
        world.scenario, id=f"scn-test-{uuid.uuid4().hex[:12]}",
        name="Gel d'origine — repris", derived_from=origin.id,
    )
    world.scenarios.create(derived)
    world.scenario = derived

    reader = held(PostgresScenarioRepository(DSN), connection)
    assert reader.get(derived.id).derived_from == origin.id
    assert reader.get(origin.scenario_id).derived_from is None

    recaptured = world.freeze("Gel repris")

    assert recaptured.derived_from == origin.id
    assert world.snapshots_repo.get(recaptured.id) == recaptured
    assert world.snapshots_repo.get(origin.id).derived_from is None


def test_starting_from_a_snapshot_in_postgres_copies_it_exactly(world, connection):
    # Le scénario du monde porte un chemin qui ne part pas de la racine, posé
    # sans validation : la reprise le refuserait, à raison.
    world.scenario = replace(
        world.scenario, id=f"scn-test-{uuid.uuid4().hex[:12]}",
        parameters=tuple(p for p in world.scenario.parameters if p.scope == "part"),
    )
    world.scenarios.create(world.scenario)
    origin = world.freeze("Gel à reprendre")
    assert len(origin.parameters) == 2
    world.scenarios.put_parameter(
        world.scenario.id,
        replace(world.scenario.parameters[0], purchase_currency="EUR"),
    )

    derived = derive_scenario(
        origin.id, "Gel à reprendre — repris",
        scenario_id=f"scn-test-{uuid.uuid4().hex[:12]}",
        snapshots_repo=world.snapshots_repo, boms=world.bom,
        scenarios=world.scenarios, sourcing=world.sourcing,
    )

    read = held(PostgresScenarioRepository(DSN), connection).get(derived.id)
    assert read == derived
    assert read.derived_from == origin.id
    assert [asdict(p) for p in read.parameters] == [
        asdict(p) for p in origin.parameters
    ]
    assert world.snapshots_repo.get(origin.id) == origin
