"""ADR-0014 sur PostgreSQL : ce que le schéma garantit d'un snapshot de calcul.

SQL brut, dans une transaction annulée : un snapshot de calcul ne se supprime
pas, un snapshot de test resterait sinon en base.
"""

import os
import uuid

import pytest

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")
VERSION = os.environ.get("CARCOST_BOM_VERSION", "bom-multipla-2026-09-22")


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


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Frozen:
    """Un scénario, deux prises de prix, deux calculs et un snapshot de calcul."""

    def __init__(self, connection):
        self.connection = connection
        self.scenario_id = unique("scn-schema")
        self.price_snapshot_ids = (unique("snp-schema"), unique("snp-schema"))
        self.calculation_ids = (unique("calc-schema"), unique("calc-schema"))
        self.part_ref = connection.execute(
            "SELECT part_ref FROM part WHERE bom_version_id = %s"
            " AND valuation_mode = 'purchased' ORDER BY part_ref LIMIT 1",
            (VERSION,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO scenario (id, bom_version_id, name, display_currency,"
            " labour_rate, labour_rate_currency)"
            " VALUES (%s, %s, 'Étude de schéma', 'EUR', 42, 'EUR')",
            (self.scenario_id, VERSION),
        )
        for price_snapshot_id in self.price_snapshot_ids:
            connection.execute(
                "INSERT INTO price_snapshot (id, taken_at, source, status, counts)"
                " VALUES (%s, now(), 'mock', 'FRESH', '{}'::jsonb)",
                (price_snapshot_id,),
            )
        for calculation_id in self.calculation_ids:
            connection.execute(
                "INSERT INTO calculation (id, scenario_id, bom_version_id,"
                " price_snapshot_id, rules_version, engine_version, active_rules,"
                " status, display_currency, total_cost, input_digest, started_at,"
                " finished_at)"
                " VALUES (%s, %s, %s, %s, 'r1', 'e1', ARRAY['labour'], 'OK', 'EUR',"
                " 100, 'sha256:schema', now(), now())",
                (calculation_id, self.scenario_id, VERSION, self.price_snapshot_ids[0]),
            )
        self.snapshot_id = self.insert_snapshot(
            self.calculation_ids[0], "Gel de référence", "gel de reference"
        )
        connection.execute(
            "INSERT INTO calculation_snapshot_parameter (snapshot_id, scope, part_ref,"
            " price_override, price_override_justification)"
            " VALUES (%s, 'part', %s, 9.5, 'devis du 2026-09-20')",
            (self.snapshot_id, self.part_ref),
        )
        connection.execute(
            "INSERT INTO calculation_snapshot_name (snapshot_id, name, renamed_at)"
            " VALUES (%s, 'Gel de référence', now())",
            (self.snapshot_id,),
        )

    def insert_snapshot(self, calculation_id: str, name: str, key: str) -> str:
        snapshot_id = unique("cs-schema")
        self.connection.execute(
            "INSERT INTO calculation_snapshot (id, name, name_key, bom_version_id,"
            " scenario_id, scenario_name, calculation_id, price_snapshot_id,"
            " display_currency, labour_rate, active_rules, created_at)"
            " VALUES (%s, %s, %s, %s, %s, 'Étude de schéma', %s, %s, 'EUR', 42,"
            " ARRAY['labour'], now())",
            (snapshot_id, name, key, VERSION, self.scenario_id, calculation_id,
             self.price_snapshot_ids[0]),
        )
        return snapshot_id


@pytest.fixture
def frozen(connection):
    return Frozen(connection)


def refused(connection, error, statement, params):
    with pytest.raises(error):
        with connection.transaction():
            connection.execute(statement, params)


def test_the_name_can_be_changed(frozen):
    frozen.connection.execute(
        "UPDATE calculation_snapshot SET name = 'Gel retenu', name_key = 'gel retenu'"
        " WHERE id = %s",
        (frozen.snapshot_id,),
    )

    row = frozen.connection.execute(
        "SELECT name, name_key FROM calculation_snapshot WHERE id = %s",
        (frozen.snapshot_id,),
    ).fetchone()
    assert row == ("Gel retenu", "gel retenu")


@pytest.mark.parametrize(
    "column", ["price_snapshot_id", "calculation_id", "scenario_name", "labour_rate"]
)
def test_a_frozen_column_cannot_change(frozen, column):
    import psycopg

    replacement = {
        "price_snapshot_id": frozen.price_snapshot_ids[1],
        "calculation_id": frozen.calculation_ids[1],
        "scenario_name": "Étude renommée",
        "labour_rate": 99,
    }[column]

    refused(
        frozen.connection,
        psycopg.errors.InsufficientPrivilege,
        f"UPDATE calculation_snapshot SET {column} = %s WHERE id = %s",
        (replacement, frozen.snapshot_id),
    )


def test_a_snapshot_cannot_be_deleted(frozen):
    import psycopg

    refused(
        frozen.connection,
        psycopg.errors.InsufficientPrivilege,
        "DELETE FROM calculation_snapshot WHERE id = %s",
        (frozen.snapshot_id,),
    )


def test_two_snapshots_cannot_share_a_name_key_in_a_version(frozen):
    import psycopg

    with pytest.raises(psycopg.errors.UniqueViolation):
        with frozen.connection.transaction():
            frozen.insert_snapshot(
                frozen.calculation_ids[1], "GEL DE RÉFÉRENCE", "gel de reference"
            )


def test_a_scenario_carrying_a_snapshot_cannot_be_deleted(frozen):
    import psycopg

    refused(
        frozen.connection,
        psycopg.errors.ForeignKeyViolation,
        "DELETE FROM scenario WHERE id = %s",
        (frozen.scenario_id,),
    )


def test_the_parameter_copy_cannot_change(frozen):
    import psycopg

    refused(
        frozen.connection,
        psycopg.errors.InsufficientPrivilege,
        "UPDATE calculation_snapshot_parameter SET price_override = 1"
        " WHERE snapshot_id = %s",
        (frozen.snapshot_id,),
    )
    refused(
        frozen.connection,
        psycopg.errors.InsufficientPrivilege,
        "DELETE FROM calculation_snapshot_parameter WHERE snapshot_id = %s",
        (frozen.snapshot_id,),
    )


def test_the_name_history_is_append_only(frozen):
    import psycopg

    refused(
        frozen.connection,
        psycopg.errors.InsufficientPrivilege,
        "UPDATE calculation_snapshot_name SET name = 'Effacé' WHERE snapshot_id = %s",
        (frozen.snapshot_id,),
    )
    refused(
        frozen.connection,
        psycopg.errors.InsufficientPrivilege,
        "DELETE FROM calculation_snapshot_name WHERE snapshot_id = %s",
        (frozen.snapshot_id,),
    )


def test_a_scenario_cannot_derive_from_an_unknown_snapshot(frozen):
    import psycopg

    refused(
        frozen.connection,
        psycopg.errors.ForeignKeyViolation,
        "UPDATE scenario SET derived_from = 'csn-inconnu' WHERE id = %s",
        (frozen.scenario_id,),
    )


def test_the_origin_of_a_snapshot_is_frozen(frozen):
    import psycopg

    other = frozen.insert_snapshot(frozen.calculation_ids[1], "Autre gel", "autre gel")

    refused(
        frozen.connection,
        psycopg.errors.InsufficientPrivilege,
        "UPDATE calculation_snapshot SET derived_from = %s WHERE id = %s",
        (other, frozen.snapshot_id),
    )
