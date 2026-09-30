"""Scénarios et leurs paramètres en base (ADR-0002)."""

from __future__ import annotations

import uuid

from ...application.ports import ScenarioNotFound
from ...application.scenario import Scenario, ScenarioParameter
from .connection import PostgresRepository


class PostgresScenarioRepository(PostgresRepository):
    def create(self, scenario: Scenario) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO scenario (id, bom_version_id, name, display_currency,
                                      labour_rate, labour_rate_currency, active_rules)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    scenario.id,
                    scenario.bom_version,
                    scenario.name,
                    scenario.display_currency,
                    scenario.labour_rate,
                    scenario.display_currency,
                    sorted(scenario.active_rules),
                ),
            )

            for parameter in scenario.parameters:
                self._put_parameter(cursor, scenario.id, parameter)

    def get(self, scenario_id: str) -> Scenario:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT bom_version_id, display_currency, labour_rate, active_rules, name
                FROM scenario WHERE id = %s
                """,
                (scenario_id,),
            )
            head = cursor.fetchone()
            if head is None:
                raise ScenarioNotFound(scenario_id)
            bom_version, currency, labour_rate, active_rules, name = head

            cursor.execute(
                """
                SELECT part_ref, scope, path, supplier_id, plant_id, price_override,
                       price_override_justification, labour_minutes, purchase_currency
                FROM scenario_parameter
                WHERE scenario_id = %s
                ORDER BY part_ref, coalesce(path, '')
                """,
                (scenario_id,),
            )
            parameters = tuple(
                ScenarioParameter(
                    part_ref=part_ref,
                    scope=scope,
                    path=path,
                    supplier_id=supplier_id,
                    plant_id=plant_id,
                    price_override=override,
                    price_override_justification=justification,
                    labour_minutes=labour_minutes,
                    purchase_currency=purchase_currency,
                )
                for (
                    part_ref, scope, path, supplier_id, plant_id, override,
                    justification, labour_minutes, purchase_currency,
                ) in cursor.fetchall()
            )

        return Scenario(
            id=scenario_id,
            bom_version=bom_version,
            display_currency=currency,
            labour_rate=labour_rate,
            active_rules=frozenset(active_rules),
            parameters=parameters,
            name=name,
        )

    def list_all(self) -> tuple[Scenario, ...]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM scenario
                ORDER BY created_at DESC, id DESC
                """
            )
            identifiers = tuple(row[0] for row in cursor.fetchall())
        return tuple(self.get(identifier) for identifier in identifiers)

    def delete(self, scenario_id: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM scenario WHERE id = %s RETURNING id", (scenario_id,)
            )
            if cursor.fetchone() is None:
                raise ScenarioNotFound(scenario_id)

    def parameter_ids(self, scenario_id: str) -> dict[tuple[str, str], str]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM scenario WHERE id = %s", (scenario_id,))
            if cursor.fetchone() is None:
                raise ScenarioNotFound(scenario_id)
            cursor.execute(
                """
                SELECT part_ref, coalesce(path, ''), id
                FROM scenario_parameter
                WHERE scenario_id = %s
                """,
                (scenario_id,),
            )
            return {
                (part_ref, path): identifier
                for part_ref, path, identifier in cursor.fetchall()
            }

    def put_parameter(self, scenario_id: str, parameter: ScenarioParameter) -> str:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM scenario WHERE id = %s", (scenario_id,))
            if cursor.fetchone() is None:
                raise ScenarioNotFound(scenario_id)
            return self._put_parameter(cursor, scenario_id, parameter)

    @staticmethod
    def _put_parameter(cursor, scenario_id: str, parameter: ScenarioParameter) -> str:
        identifier = f"prm-{uuid.uuid4().hex[:12]}"
        cursor.execute(
            """
            INSERT INTO scenario_parameter
                (id, scenario_id, scope, part_ref, path, supplier_id, plant_id,
                 price_override, price_override_justification, labour_minutes,
                 purchase_currency)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (scenario_id, part_ref, coalesce(path, ''))
            DO UPDATE SET
                scope = EXCLUDED.scope,
                supplier_id = EXCLUDED.supplier_id,
                plant_id = EXCLUDED.plant_id,
                price_override = EXCLUDED.price_override,
                price_override_justification = EXCLUDED.price_override_justification,
                labour_minutes = EXCLUDED.labour_minutes,
                purchase_currency = EXCLUDED.purchase_currency
            RETURNING id
            """,
            (
                identifier,
                scenario_id,
                parameter.scope,
                parameter.part_ref,
                parameter.path,
                parameter.supplier_id,
                parameter.plant_id,
                parameter.price_override,
                parameter.price_override_justification,
                parameter.labour_minutes,
                parameter.purchase_currency,
            ),
        )
        return cursor.fetchone()[0]

    def delete_parameter(self, scenario_id: str, parameter_id: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM scenario_parameter WHERE scenario_id = %s AND id = %s",
                (scenario_id, parameter_id),
            )
