"""Snapshots de calcul en base (ADR-0014).

Un gel s'écrit d'un bloc : le snapshot, la copie de ses paramètres et la
première ligne de l'historique des noms, dans une seule transaction. Rien en
SQL n'écrit cette première ligne. L'adaptateur n'écrit que ce que l'entité
porte : il ne vérifie pas que les références du gel sont celles de son calcul,
c'est le cas d'usage qui les en tire.

Ordre des listes : `list_for` et `for_scenario` rendent du plus récent au plus
ancien (`created_at` décroissant, puis `id` décroissant pour départager). C'est
l'ordre que reprend `ScenarioHasSnapshots.names`.

Le nom se plie dans le domaine (`name_key`) ; la base n'en garantit que
l'unicité, et une `UniqueViolation` sur cette clé devient `SnapshotNameTaken`.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import errors

from ...application.ports import CalculationSnapshotNotFound, SnapshotNameTaken
from ...domain.calculation_snapshot import (
    CalculationSnapshot, FrozenParameter, name_key,
)
from .connection import PostgresRepository

_NAME_UNIQUE = "calculation_snapshot_name_uq"

_COLUMNS = """
    id, name, bom_version_id, scenario_id, scenario_name, calculation_id,
    price_snapshot_id, display_currency, labour_rate, active_rules, created_at,
    derived_from
"""


class PostgresCalculationSnapshotRepository(PostgresRepository):
    def save(self, snapshot: CalculationSnapshot) -> None:
        with self._connect() as connection:
            try:
                # Un point de sauvegarde si la connexion est déjà dans une
                # transaction : le refus n'abandonne pas ce qui l'entoure.
                with connection.transaction():
                    self._insert(connection, snapshot)
            except errors.UniqueViolation as refused:
                if refused.diag.constraint_name != _NAME_UNIQUE:
                    raise
                raise SnapshotNameTaken(
                    snapshot.name,
                    self._holder(connection, snapshot.bom_version, snapshot.name),
                ) from refused

    def get(self, snapshot_id: str) -> CalculationSnapshot:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM calculation_snapshot WHERE id = %s",
                (snapshot_id,),
            ).fetchone()
            if row is None:
                raise CalculationSnapshotNotFound(snapshot_id)
            return self._build(connection, row)

    def list_for(self, bom_version: str) -> tuple[CalculationSnapshot, ...]:
        return self._list("bom_version_id", bom_version)

    def for_scenario(self, scenario_id: str) -> tuple[CalculationSnapshot, ...]:
        return self._list("scenario_id", scenario_id)

    def rename(self, snapshot_id: str, name: str, renamed_at: datetime) -> None:
        with self._connect() as connection:
            try:
                with connection.transaction():
                    row = connection.execute(
                        "UPDATE calculation_snapshot SET name = %s, name_key = %s"
                        " WHERE id = %s RETURNING id",
                        (name, name_key(name), snapshot_id),
                    ).fetchone()
                    if row is None:
                        raise CalculationSnapshotNotFound(snapshot_id)
                    connection.execute(
                        "INSERT INTO calculation_snapshot_name"
                        " (snapshot_id, name, renamed_at) VALUES (%s, %s, %s)",
                        (snapshot_id, name, renamed_at),
                    )
            except errors.UniqueViolation as refused:
                if refused.diag.constraint_name != _NAME_UNIQUE:
                    raise
                raise SnapshotNameTaken(
                    name,
                    self._holder(connection, _version_of(connection, snapshot_id), name),
                ) from refused

    def name_history(self, snapshot_id: str) -> tuple[tuple[str, datetime], ...]:
        with self._connect() as connection:
            known = connection.execute(
                "SELECT 1 FROM calculation_snapshot WHERE id = %s", (snapshot_id,),
            ).fetchone()
            if known is None:
                raise CalculationSnapshotNotFound(snapshot_id)
            rows = connection.execute(
                "SELECT name, renamed_at FROM calculation_snapshot_name"
                " WHERE snapshot_id = %s ORDER BY seq",
                (snapshot_id,),
            ).fetchall()
            return tuple((name, renamed_at) for name, renamed_at in rows)

    def _list(self, column: str, value: str) -> tuple[CalculationSnapshot, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM calculation_snapshot WHERE {column} = %s"
                " ORDER BY created_at DESC, id DESC",
                (value,),
            ).fetchall()
            return tuple(self._build(connection, row) for row in rows)

    @staticmethod
    def _insert(connection, snapshot: CalculationSnapshot) -> None:
        connection.execute(
            """
            INSERT INTO calculation_snapshot
                (id, name, name_key, bom_version_id, scenario_id, calculation_id,
                 price_snapshot_id, scenario_name, display_currency, labour_rate,
                 active_rules, created_at, derived_from)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                snapshot.id, snapshot.name, snapshot.name_key, snapshot.bom_version,
                snapshot.scenario_id, snapshot.calculation_id,
                snapshot.price_snapshot_id, snapshot.scenario_name,
                snapshot.display_currency, snapshot.labour_rate,
                sorted(snapshot.active_rules), snapshot.created_at,
                snapshot.derived_from,
            ),
        )
        for parameter in snapshot.parameters:
            connection.execute(
                """
                INSERT INTO calculation_snapshot_parameter
                    (snapshot_id, scope, part_ref, path, supplier_id, plant_id,
                     purchase_currency, price_override,
                     price_override_justification, labour_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    snapshot.id, parameter.scope, parameter.part_ref, parameter.path,
                    parameter.supplier_id, parameter.plant_id,
                    parameter.purchase_currency, parameter.price_override,
                    parameter.price_override_justification, parameter.labour_minutes,
                ),
            )
        connection.execute(
            "INSERT INTO calculation_snapshot_name (snapshot_id, name, renamed_at)"
            " VALUES (%s, %s, %s)",
            (snapshot.id, snapshot.name, snapshot.created_at),
        )

    @staticmethod
    def _build(connection, row) -> CalculationSnapshot:
        (
            identifier, name, bom_version, scenario_id, scenario_name,
            calculation_id, price_snapshot_id, currency, labour_rate,
            active_rules, created_at, derived_from,
        ) = row
        parameters = connection.execute(
            """
            SELECT part_ref, scope, path, supplier_id, plant_id, price_override,
                   price_override_justification, labour_minutes, purchase_currency
            FROM calculation_snapshot_parameter
            WHERE snapshot_id = %s
            ORDER BY part_ref, scope, coalesce(path, '')
            """,
            (identifier,),
        ).fetchall()
        return CalculationSnapshot(
            id=identifier,
            name=name,
            bom_version=bom_version,
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            calculation_id=calculation_id,
            price_snapshot_id=price_snapshot_id,
            display_currency=currency,
            labour_rate=labour_rate,
            active_rules=frozenset(active_rules),
            parameters=tuple(
                FrozenParameter(
                    part_ref=part_ref, scope=scope, path=path,
                    supplier_id=supplier_id, plant_id=plant_id,
                    price_override=override,
                    price_override_justification=justification,
                    labour_minutes=minutes, purchase_currency=purchase_currency,
                )
                for (
                    part_ref, scope, path, supplier_id, plant_id, override,
                    justification, minutes, purchase_currency,
                ) in parameters
            ),
            created_at=created_at,
            derived_from=derived_from,
        )

    @staticmethod
    def _holder(connection, bom_version: str, name: str) -> str:
        """L'identifiant du snapshot qui porte déjà ce nom, pour le message."""
        row = connection.execute(
            "SELECT id FROM calculation_snapshot"
            " WHERE bom_version_id = %s AND name_key = %s",
            (bom_version, name_key(name)),
        ).fetchone()
        return row[0]


def _version_of(connection, snapshot_id: str) -> str:
    return connection.execute(
        "SELECT bom_version_id FROM calculation_snapshot WHERE id = %s",
        (snapshot_id,),
    ).fetchone()[0]
