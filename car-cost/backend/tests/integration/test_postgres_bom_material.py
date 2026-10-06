"""Matière, densité et parenté lues en base sur le vrai Multipla (ADR-0017)."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")
VERSION = os.environ.get("CARCOST_BOM_VERSION", "bom-multipla-2026-09-22")


@pytest.fixture(scope="module")
def repository():
    psycopg = pytest.importorskip("psycopg")
    from carcost.infrastructure.postgres.bom import PostgresBomRepository

    try:
        with psycopg.connect(DSN, connect_timeout=3):
            pass
    except Exception as unreachable:  # noqa: BLE001
        pytest.skip(f"Postgres injoignable : {unreachable}")
    return PostgresBomRepository(DSN)


def test_postgres_bom_reads_material_and_density(repository):
    bom = repository.load(VERSION)

    assert bom.parts["MAT-ALU-SHEET"].density_kg_m3 == Decimal("2700")
    assert bom.parts["CAR-HOOD-SHELL"].material_ref == "MAT-STEEL-SHEET"
    assert bom.parts["MAT-PAINT-BASE"].density_kg_m3 is None


def test_versions_expose_no_parent_for_the_loaded_versions(repository):
    versions = repository.versions()

    assert len(versions) >= 4
    assert all(version.parent_version_id is None for version in versions)
