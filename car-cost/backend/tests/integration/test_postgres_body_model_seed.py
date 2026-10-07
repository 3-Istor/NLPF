"""La maquette générée du Multipla, chargée en base avec le jeu de données.

Lecture seule : la base a été chargée par `python -m carcost.infrastructure seeds`.
"""

import hashlib
import os
from pathlib import Path

import pytest

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")
MOCKUP = Path(__file__).resolve().parents[3] / "seeds" / "body_multipla.glb"


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


def test_postgres_stores_the_generated_mockup(connection):
    data = MOCKUP.read_bytes()

    row = connection.execute(
        "SELECT source, sha256, glb FROM bom_model"
        " WHERE bom_version_id = 'bom-multipla-2026-09-22'"
    ).fetchone()
    valhalla = connection.execute(
        "SELECT count(*), count(m.bom_version_id) FROM bom_version v"
        " LEFT JOIN bom_model m ON m.bom_version_id = v.id"
        " WHERE v.id LIKE 'bom-valhalla-%'"
    ).fetchone()

    assert row is not None
    source, digest, glb = row
    assert source == "generated"
    assert digest == hashlib.sha256(data).hexdigest()
    assert bytes(glb) == data
    assert valhalla == (3, 0)
