"""Écriture d'une variante de carrosserie sur le vrai Multipla (ADR-0017 §6).

Le plan vient des vraies fonctions (`plan_variant` sur la nomenclature lue en
base). Une variante validée ne se supprime pas : chaque test a son identifiant,
et la suite tourne deux fois sur la même base. Prix, densités et maquette sont
synthétiques.
"""

from __future__ import annotations

import hashlib
import os
import threading
import uuid
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest

from carcost.application.body_import import NewPart, plan_variant
from carcost.application.body_model import BodyModel, ModelObject
from carcost.application.ports import NewVariant, VariantIdCollision
from carcost.infrastructure.gltf_reader import read_glb
from gltf_builder import f32
from real_multipla import MULTIPLA, mockup_bytes

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")
VALHALLA = "bom-valhalla-hybride-2026-10-05"


@pytest.fixture(scope="module")
def world():
    psycopg = pytest.importorskip("psycopg")
    from carcost.infrastructure.postgres.body_models import PostgresBodyModelRepository
    from carcost.infrastructure.postgres.bom import PostgresBomRepository
    from carcost.infrastructure.postgres.variants import PostgresVariantWriter

    try:
        with psycopg.connect(DSN, connect_timeout=3):
            pass
    except Exception as unreachable:  # noqa: BLE001
        pytest.skip(f"Postgres injoignable : {unreachable}")
    yield {
        "bom": PostgresBomRepository(DSN),
        "writer": PostgresVariantWriter(DSN),
        "models": PostgresBodyModelRepository(DSN),
    }
    forget_variants()


CREATED: list[str] = []


def forget_variants() -> None:
    """Une variante validée est figée : seul le rôle « replica » permet de retirer celles du test.

    Sans cela elles resteraient dans la base partagée et fausseraient les tests
    qui supposent que les versions chargées n'ont pas de parente.
    """
    import psycopg

    with psycopg.connect(DSN) as connection:
        connection.execute("SET LOCAL session_replication_role = replica")
        for table, column in [("bom_model", "bom_version_id"), ("part_supplier", "bom_version_id"),
                              ("bom_edge", "bom_version_id"), ("part", "bom_version_id"),
                              ("bom_version", "id")]:
            connection.execute(f"DELETE FROM {table} WHERE {column} = ANY(%s)", (CREATED,))


@pytest.fixture
def db():
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as connection:
        yield connection


def spoiler_model() -> BodyModel:
    mockup = read_glb(mockup_bytes())
    volume = Fraction(f32(1.2)) * Fraction(0.25) * Fraction(f32(0.01))
    return BodyModel(mockup.objects + (ModelObject(
        node_index=1000, name="Aileron", mesh_index=1000, materials=("MAT-ABS-GRANULE",),
        spec={"ref": "BODY-SPOILER", "parts": {"FIX-M8-20": "4"}}, volume_m3=volume, is_closed=True,
    ),))


def new_variant(world, plan=None) -> NewVariant:
    plan = plan or plan_variant(world["bom"].load(MULTIPLA), spoiler_model())
    glb = b"glTF-synthetique-" + uuid.uuid4().bytes
    CREATED.append(f"{MULTIPLA}+t{uuid.uuid4().hex[:7]}")
    return NewVariant(CREATED[-1], "variante de test", MULTIPLA, hashlib.sha256(glb).hexdigest(), glb, plan)


def offers(db, version):
    return db.execute(
        "SELECT part_ref, supplier_id, price_multiplier FROM part_supplier"
        " WHERE bom_version_id = %s ORDER BY 1, 2", (version,)).fetchall()


def test_saved_variant_reloads_as_planned(world, db):
    variant = new_variant(world)

    world["writer"].save_variant(variant)

    loaded = world["bom"].load(variant.id)
    assert set(loaded.parts) == set(variant.plan.bom.parts)
    assert set(loaded.edges) == set(variant.plan.bom.edges)
    summary = next(v for v in world["bom"].versions() if v.id == variant.id)
    assert summary.parent_version_id == MULTIPLA
    cumulative = db.execute(
        "SELECT expected_cumulative_quantity FROM part"
        " WHERE bom_version_id = %s AND part_ref = 'FIX-M8-20'", (variant.id,)).fetchone()[0]
    assert cumulative == Decimal(208)
    assert offers(db, variant.id) == offers(db, MULTIPLA) != []


def test_saved_variant_is_frozen(world, db):
    import psycopg

    variant = new_variant(world)
    world["writer"].save_variant(variant)

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("UPDATE part SET label = 'x' WHERE bom_version_id = %s", (variant.id,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("DELETE FROM bom_version WHERE id = %s", (variant.id,))


def test_saved_model_is_immutable(world, db):
    import psycopg

    variant = new_variant(world)
    world["writer"].save_variant(variant)

    stored = world["models"].get(variant.id)
    assert (stored.glb, stored.sha256, stored.source) == (variant.glb, variant.sha256, "imported")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("UPDATE bom_model SET source = 'generated' WHERE bom_version_id = %s", (variant.id,))


def test_failed_save_leaves_no_row(world, db):
    import psycopg

    good = plan_variant(world["bom"].load(MULTIPLA), spoiler_model())
    parts = dict(good.bom.parts)
    parts["bad ref"] = replace(parts["BODY-SPOILER"], ref="bad ref")
    bad = replace(good, bom=replace(good.bom, parts=parts, edges=good.bom.edges + (
        replace(good.bom.edges[0], child_ref="bad ref"),)),
        new_parts=good.new_parts + (replace(good.new_parts[0], ref="bad ref"),),
        cumulative={**good.cumulative, "bad ref": Decimal(1)})
    variant = new_variant(world, bad)

    with pytest.raises(psycopg.errors.CheckViolation):  # le domaine part_reference refuse « bad ref »
        world["writer"].save_variant(variant)

    for table, column in [("bom_version", "id"), ("part", "bom_version_id"), ("bom_edge", "bom_version_id"),
                          ("part_supplier", "bom_version_id"), ("bom_model", "bom_version_id")]:
        assert db.execute(f"SELECT count(*) FROM {table} WHERE {column} = %s", (variant.id,)).fetchone()[0] == 0


def fingerprint(db, version):
    rows = [
        db.execute(f"SELECT count(*), md5(string_agg(t::text, '|' ORDER BY t::text)) FROM {table} t"
                   f" WHERE bom_version_id = %s", (version,)).fetchone()
        for table in ("part", "bom_edge", "part_supplier")
    ]
    rows.append(db.execute("SELECT bom_version::text FROM bom_version WHERE id = %s", (version,)).fetchone())
    return rows


def test_parent_is_unchanged(world, db):
    before = fingerprint(db, MULTIPLA)

    world["writer"].save_variant(new_variant(world))

    assert fingerprint(db, MULTIPLA) == before


def test_model_repository_returns_none_for_a_version_without_model(world):
    assert world["models"].get(VALHALLA) is None


def test_same_file_saved_twice_writes_once_and_a_clash_is_refused(world, db):
    variant = new_variant(world)
    world["writer"].save_variant(variant)

    world["writer"].save_variant(variant)  # même fichier : rien de plus

    assert db.execute("SELECT count(*) FROM bom_version WHERE id = %s", (variant.id,)).fetchone()[0] == 1
    other = hashlib.sha256(b"autre").hexdigest()
    with pytest.raises(VariantIdCollision):
        world["writer"].save_variant(replace(variant, sha256=other, glb=b"autre"))


def test_two_simultaneous_imports_of_the_same_file_write_one_variant(world, db):
    variant = new_variant(world)
    barrier, errors = threading.Barrier(2), []

    def save():
        barrier.wait()
        try:
            world["writer"].save_variant(variant)
        except Exception as failure:  # noqa: BLE001
            errors.append(failure)

    threads = [threading.Thread(target=save) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert errors == []
    assert db.execute("SELECT count(*) FROM bom_version WHERE id = %s", (variant.id,)).fetchone()[0] == 1
    assert world["bom"].load(variant.id).parts.keys() == variant.plan.bom.parts.keys()
