"""ADR-0017 sur PostgreSQL : ce que le schéma garantit d'un modèle 3D rattaché.

SQL brut, dans une transaction annulée, sur une version de test propre à chaque
test (jamais le Multipla). Le contenu du modèle est un octet quelconque : la base
n'en lit pas le glTF, elle garde seulement sa somme de contrôle (intégrité).
"""

import hashlib
import os
import uuid

import pytest

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")
GLB = b"glTF-synthetique"
DIGEST = hashlib.sha256(GLB).hexdigest()


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


def insert_version(connection, validated: bool = True) -> str:
    version_id = unique("bom-schema-3d")
    connection.execute(
        "INSERT INTO bom_version (id, label, root_part_ref, generator_version,"
        " seed_checksum, part_count, edge_count)"
        " VALUES (%s, 'test 3D', 'ROOT', '1.0.0', 'sha256:x', 1, 1)",
        (version_id,),
    )
    connection.execute(
        "INSERT INTO part (bom_version_id, part_ref, label, category, system, unit,"
        " valuation_mode, labour_minutes, carbon_factor_kg_co2e_per_unit,"
        " expected_cumulative_quantity)"
        " VALUES (%s, 'ROOT', 'Racine', 'vehicle', 'VEH', 'pce', 'manufactured',"
        " 10, 1, 1)",
        (version_id,),
    )
    if validated:
        connection.execute(
            "UPDATE bom_version SET validated_at = now() WHERE id = %s", (version_id,)
        )
    return version_id


def insert_model(connection, version_id: str, digest: str = DIGEST, source="generated"):
    connection.execute(
        "INSERT INTO bom_model (bom_version_id, glb, sha256, source)"
        " VALUES (%s, %s, %s, %s)",
        (version_id, GLB, digest, source),
    )


def refused(connection, error, statement, params):
    with pytest.raises(error):
        with connection.transaction():
            connection.execute(statement, params)


def test_a_model_can_be_attached_to_a_validated_version(connection):
    version_id = insert_version(connection)

    insert_model(connection, version_id)

    count = connection.execute(
        "SELECT count(*) FROM bom_model WHERE bom_version_id = %s", (version_id,)
    ).fetchone()[0]
    assert count == 1


def test_an_attached_model_cannot_be_updated(connection):
    import psycopg

    version_id = insert_version(connection)
    insert_model(connection, version_id)

    refused(
        connection,
        psycopg.errors.InsufficientPrivilege,
        "UPDATE bom_model SET source = 'imported' WHERE bom_version_id = %s",
        (version_id,),
    )


def test_an_attached_model_cannot_be_deleted(connection):
    import psycopg

    version_id = insert_version(connection)
    insert_model(connection, version_id)

    refused(
        connection,
        psycopg.errors.InsufficientPrivilege,
        "DELETE FROM bom_model WHERE bom_version_id = %s",
        (version_id,),
    )


def test_a_model_whose_digest_does_not_match_is_refused(connection):
    import psycopg

    version_id = insert_version(connection)

    refused(
        connection,
        psycopg.errors.CheckViolation,
        "INSERT INTO bom_model (bom_version_id, glb, sha256, source)"
        " VALUES (%s, %s, %s, 'generated')",
        (version_id, GLB, hashlib.sha256(b"autre chose").hexdigest()),
    )


def test_a_density_must_be_positive(connection):
    import psycopg

    version_id = insert_version(connection, validated=False)

    refused(
        connection,
        psycopg.errors.CheckViolation,
        "INSERT INTO part (bom_version_id, part_ref, label, category, system, unit,"
        " valuation_mode, labour_minutes, carbon_factor_kg_co2e_per_unit,"
        " expected_cumulative_quantity, density_kg_m3)"
        " VALUES (%s, 'DENSE', 'Dense', 'body', 'CAR', 'pce', 'manufactured',"
        " 1, 1, 1, 0)",
        (version_id,),
    )


def test_a_parent_version_must_exist(connection):
    import psycopg

    refused(
        connection,
        psycopg.errors.ForeignKeyViolation,
        "INSERT INTO bom_version (id, label, root_part_ref, generator_version,"
        " seed_checksum, part_count, edge_count, parent_version_id)"
        " VALUES (%s, 'orpheline', 'ROOT', '1.0.0', 'sha256:x', 1, 1, 'inconnue')",
        (unique("bom-schema-3d"),),
    )
