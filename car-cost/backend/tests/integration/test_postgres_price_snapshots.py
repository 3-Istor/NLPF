"""Un snapshot dégradé, écrit puis relu dans un vrai Postgres.

Le défaut que ces tests ferment n'était visible qu'avec une base : le double en
mémoire rendait l'objet tel quel, alors que la relecture en base perdait
l'origine des lignes. Le snapshot `--fail outlier` repassait pour frais, et le
calcul fait dessus sortait `OK`.

Tout se déroule dans une transaction **annulée** à la fin : un snapshot ne se
supprime pas (déclencheur), et un test qui écrirait pour de bon laisserait
derrière lui un snapshot que `latest()` servirait ensuite à l'écran.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from carcost.application.ports import PriceSnapshotNotFound
from carcost.application.price_resolution import resolve_unit_prices
from carcost.application.run_calculation import PriceStatus, run_calculation
from carcost.application.scenario import Scenario
from carcost.application.take_snapshot import QuarantinedPrice
from carcost.domain.prices import PriceSnapshot, SnapshotStatus

DSN = os.environ.get(
    "CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor"
)
VERSION = os.environ.get("CARCOST_BOM_VERSION", "bom-multipla-2026-09-22")
NOW = datetime.now(timezone.utc)


class _Held:
    """La connexion du test, prêtée sans être validée ni fermée à la sortie."""

    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_):
        return False


@pytest.fixture
def connection():
    psycopg = pytest.importorskip("psycopg")
    try:
        connection = psycopg.connect(DSN, connect_timeout=3)
    except Exception as unreachable:  # noqa: BLE001 - on saute, on n'échoue pas
        pytest.skip(f"Postgres injoignable : {unreachable}")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def held(repository, connection):
    repository._connect = lambda: _Held(connection)
    return repository


@pytest.fixture
def snapshots(connection):
    from carcost.infrastructure.postgres_repositories import (
        PostgresPriceSnapshotRepository,
    )

    return held(PostgresPriceSnapshotRepository(DSN), connection)


@pytest.fixture
def two_purchased(connection):
    """Deux pièces achetées réelles : le journal et les lignes de calcul
    portent des clés vers la nomenclature."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT part_ref FROM part WHERE bom_version_id = %s "
            "AND valuation_mode = 'purchased' ORDER BY part_ref LIMIT 2",
            (VERSION,),
        )
        refs = [row[0] for row in cursor.fetchall()]
    assert len(refs) == 2, "nomenclature non chargée"
    return refs


def save_degraded(snapshots, fresh_ref, refused_ref):
    yesterday = PriceSnapshot(
        id="snp-test-hier", taken_at=NOW, currency="EUR", source="test",
        prices={fresh_ref: Decimal("1.000000"), refused_ref: Decimal("4.200000")},
    )
    today = PriceSnapshot(
        id="snp-test-jour", taken_at=NOW, currency="EUR", source="test",
        prices={fresh_ref: Decimal("1.100000"), refused_ref: Decimal("4.200000")},
        fallback_refs=frozenset({refused_ref}),
        quarantined_refs=frozenset({refused_ref}),
    )
    snapshots.save(yesterday)
    snapshots.save(
        today,
        quarantined=(
            QuarantinedPrice(
                part_ref=refused_ref, rejected_value="-42.000000",
                reason="prix négatif", replacement=Decimal("4.200000"),
            ),
        ),
        previous_id=yesterday.id,
    )
    return today


class TestReadingBack:
    def test_snapshots_are_listed_newest_first(self, snapshots, two_purchased):
        save_degraded(snapshots, *two_purchased)

        listed = [
            snapshot
            for snapshot in snapshots.list_all()
            if snapshot.id in {"snp-test-hier", "snp-test-jour"}
        ]

        assert [snapshot.id for snapshot in listed] == [
            "snp-test-jour", "snp-test-hier"
        ]
        assert listed[0].status(NOW) is SnapshotStatus.DEGRADED

    def test_a_degraded_snapshot_is_still_degraded_once_read_back(
        self, snapshots, two_purchased
    ):
        fresh_ref, refused_ref = two_purchased
        save_degraded(snapshots, fresh_ref, refused_ref)

        read = snapshots.get("snp-test-jour")

        assert read.fallback_refs == frozenset({refused_ref})
        assert read.quarantined_refs == frozenset({refused_ref})
        assert read.status(NOW) is SnapshotStatus.DEGRADED

    def test_a_clean_snapshot_reads_back_clean(self, snapshots, two_purchased):
        save_degraded(snapshots, *two_purchased)

        read = snapshots.get("snp-test-hier")

        assert read.fallback_refs == frozenset()
        assert read.status(NOW) is SnapshotStatus.FRESH

    def test_the_journal_reads_back_typed_and_traced(self, snapshots, two_purchased):
        _, refused_ref = two_purchased
        save_degraded(snapshots, *two_purchased)

        (record,) = snapshots.quarantine_of("snp-test-jour")

        assert record.part_ref == refused_ref
        assert record.rejected_value == "-42.000000"
        assert record.replacement == Decimal("4.200000")
        assert record.replacement_from_snapshot == "snp-test-hier"

    def test_an_unknown_snapshot_has_no_journal_at_all(self, snapshots):
        with pytest.raises(PriceSnapshotNotFound):
            snapshots.quarantine_of("snp-qui-n-existe-pas")


class TestCalculationLines:
    def test_each_line_keeps_the_origin_of_its_price(self, connection, two_purchased):
        from carcost.infrastructure.postgres_bom_repository import (
            PostgresBomRepository,
        )
        from carcost.infrastructure.postgres_repositories import (
            PostgresCalculationRepository,
            PostgresPriceSnapshotRepository,
            PostgresScenarioRepository,
            PostgresSourcingRepository,
        )

        fresh_ref, refused_ref = two_purchased
        snapshots = held(PostgresPriceSnapshotRepository(DSN), connection)
        save_degraded(snapshots, fresh_ref, refused_ref)
        snapshot = snapshots.get("snp-test-jour")

        # En lecture seule, et déjà validée en base : pas besoin de la transaction.
        bom = PostgresBomRepository(DSN).load(VERSION)
        sourcing = held(PostgresSourcingRepository(DSN), connection).load(VERSION)
        scenario = Scenario(
            id="scn-test-quarantaine", bom_version=VERSION,
            display_currency="EUR", labour_rate=Decimal("42.00"),
        )
        held(PostgresScenarioRepository(DSN), connection).create(scenario)

        calculation = run_calculation(
            bom=bom, scenario=scenario, snapshot=snapshot,
            resolved=resolve_unit_prices(bom, sourcing, snapshot, scenario),
            now=NOW, calculation_id="calc-test-quarantaine",
        )
        calculations = held(PostgresCalculationRepository(DSN), connection)
        calculations.save(calculation)

        read = calculations.get("calc-test-quarantaine")

        assert read.price_status_of(fresh_ref) is PriceStatus.OK
        assert read.price_status_of(refused_ref) is PriceStatus.QUARANTINED
        # Toutes les autres pièces achetées sont sans prix dans ce snapshot de
        # deux lignes : elles le restent à la relecture, et aucune n'a pris zéro.
        assert read.issue_counts() == calculation.issue_counts()
        assert read.issue_counts()["missing_price"] > 0

    def test_a_path_override_keeps_its_own_cost_once_read_back(
        self, connection, two_purchased
    ):
        """L'arbre est servi depuis le calcul relu : si les coûts de contexte
        se perdaient en base, chaque occurrence afficherait la moyenne pondérée
        de la ligne agrégée, et l'écran contredirait la surcharge de chemin."""
        from carcost.application.browse_bom import where_used
        from carcost.application.scenario import ScenarioParameter
        from carcost.infrastructure.postgres_bom_repository import (
            PostgresBomRepository,
        )
        from carcost.infrastructure.postgres_repositories import (
            PostgresCalculationRepository,
            PostgresPriceSnapshotRepository,
            PostgresScenarioRepository,
            PostgresSourcingRepository,
        )

        fresh_ref, refused_ref = two_purchased
        snapshots = held(PostgresPriceSnapshotRepository(DSN), connection)
        save_degraded(snapshots, fresh_ref, refused_ref)
        snapshot = snapshots.get("snp-test-jour")
        bom = PostgresBomRepository(DSN).load(VERSION)
        sourcing = held(PostgresSourcingRepository(DSN), connection).load(VERSION)

        shared = next(
            ref for ref, part in sorted(bom.parts.items())
            if part.is_purchased and where_used(bom, ref, limit=2).total > 1
        )
        overridden = where_used(bom, shared, limit=1).items[0].path
        scenario = Scenario(
            id="scn-test-chemin", bom_version=VERSION,
            display_currency="EUR", labour_rate=Decimal("42.00"),
            parameters=(
                ScenarioParameter(
                    part_ref=shared, price_override=Decimal("1.000000"),
                    price_override_justification="devis cadre",
                ),
                ScenarioParameter(
                    part_ref=shared, scope="path", path=overridden,
                    price_override=Decimal("5.000000"),
                    price_override_justification="sous-ensemble sourcé ailleurs",
                ),
            ),
        )
        held(PostgresScenarioRepository(DSN), connection).create(scenario)
        calculation = run_calculation(
            bom=bom, scenario=scenario, snapshot=snapshot,
            resolved=resolve_unit_prices(bom, sourcing, snapshot, scenario),
            now=NOW, calculation_id="calc-test-chemin",
        )
        calculations = held(PostgresCalculationRepository(DSN), connection)
        calculations.save(calculation)

        read = calculations.get("calc-test-chemin")

        assert calculation.path_own_unit_costs[overridden] == Decimal("5")
        assert read.path_own_unit_costs == calculation.path_own_unit_costs
        assert read.path_full_unit_costs == calculation.path_full_unit_costs
        assert read.part_own_unit_costs[shared] == Decimal("1")
        assert read.part_full_unit_costs[shared] == Decimal("1")
