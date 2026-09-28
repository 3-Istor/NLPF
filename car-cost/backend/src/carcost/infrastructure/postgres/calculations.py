"""Calculs enregistrés en base.

Un calcul s'insère une fois, complet, et ne se modifie plus (ADR-0003). Ce
qui se déduit de ses lignes n'est pas stocké en double.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from ...application.ports import CalculationNotFound
from ...application.price_resolution import PriceExplanation
from ...application.run_calculation import (
    Calculation,
    CalculationStatus,
    PriceStatus,
    SystemTotal,
)
from ...domain.engine import PartLine
from .connection import PostgresRepository


class PostgresCalculationRepository(PostgresRepository):
    def save(self, calculation: Calculation) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO calculation
                    (id, scenario_id, bom_version_id, price_snapshot_id,
                     rules_version, engine_version, active_rules, status,
                     display_currency, total_cost, input_digest,
                     started_at, finished_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    calculation.id,
                    calculation.scenario_id,
                    calculation.bom_version,
                    calculation.snapshot_id,
                    calculation.rules_version,
                    calculation.engine_version,
                    list(calculation.active_rules),
                    calculation.status.value,
                    calculation.display_currency,
                    calculation.total_cost,
                    calculation.input_digest,
                    calculation.computed_at,
                    calculation.computed_at,
                ),
            )

            with cursor.copy(
                "COPY calculation_line (calculation_id, part_ref, "
                "cumulative_quantity, unit, unit_cost, own_unit_cost, "
                "own_contribution, occurrence_count, price_status, supplier_id, "
                "plant_id) FROM STDIN"
            ) as copy:
                for line in calculation.lines:
                    explanation = calculation.explanations.get(line.part_ref)
                    copy.write_row(
                        (
                            calculation.id,
                            line.part_ref,
                            line.cumulative_quantity,
                            "pce",
                            line.full_unit_cost,
                            line.own_unit_cost,
                            line.own_contribution,
                            line.occurrence_count,
                            calculation.price_status_of(line.part_ref).value,
                            explanation.supplier_id if explanation else None,
                            explanation.plant_id if explanation else None,
                        )
                    )

            with cursor.copy(
                "COPY calculation_system_total (calculation_id, system, cost, co2, "
                "cost_share_pct, co2_share_pct) FROM STDIN"
            ) as copy:
                for system in calculation.systems:
                    copy.write_row(
                        (
                            calculation.id,
                            system.system,
                            system.cost,
                            Decimal(0),
                            system.share_pct,
                            Decimal(0),
                        )
                    )

            for part_ref in calculation.parts_without_price:
                cursor.execute(
                    """
                    INSERT INTO calculation_issue
                        (calculation_id, kind, part_ref, detail)
                    VALUES (%s, 'MISSING_PRICE', %s, %s)
                    """,
                    (calculation.id, part_ref, "aucun prix connu pour cette pièce"),
                )

    def get(self, calculation_id: str) -> Calculation:
        calculation = self._read(calculation_id)
        if calculation is None:
            raise CalculationNotFound(calculation_id)
        return calculation

    def latest_for(self, scenario_id: str) -> Calculation | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM calculation
                WHERE scenario_id = %s
                ORDER BY finished_at DESC, id DESC
                LIMIT 1
                """,
                (scenario_id,),
            )
            row = cursor.fetchone()
        return self._read(row[0]) if row else None

    def _read(self, calculation_id: str) -> Calculation | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.scenario_id, c.bom_version_id, c.price_snapshot_id,
                       c.rules_version, c.engine_version, c.active_rules, c.status,
                       c.display_currency, c.total_cost, c.input_digest,
                       c.finished_at, s.taken_at, s.status
                FROM calculation c
                LEFT JOIN price_snapshot s ON s.id = c.price_snapshot_id
                WHERE c.id = %s
                """,
                (calculation_id,),
            )
            head = cursor.fetchone()
            if head is None:
                return None
            (
                scenario_id, bom_version, snapshot_id, rules_version, engine_version,
                active_rules, status, currency, total, digest, finished_at,
                snapshot_taken_at, snapshot_status,
            ) = head

            cursor.execute(
                """
                SELECT part_ref, cumulative_quantity, occurrence_count, unit_cost,
                       own_unit_cost, own_contribution, supplier_id, plant_id,
                       price_status
                FROM calculation_line
                WHERE calculation_id = %s
                ORDER BY part_ref
                """,
                (calculation_id,),
            )
            rows = cursor.fetchall()
            lines = tuple(
                PartLine(
                    part_ref=part_ref,
                    cumulative_quantity=quantity,
                    occurrence_count=occurrences,
                    own_unit_cost=own_unit,
                    own_contribution=own,
                    full_unit_cost=full,
                )
                for part_ref, quantity, occurrences, full, own_unit, own, _, _, _
                in rows
            )
            # Relu tel qu'il a été écrit, pas recalculé depuis le snapshot : le
            # calcul dit ce qu'il a vu, et un snapshot n'est de toute façon
            # jamais modifié.
            price_statuses = {
                row[0]: PriceStatus(row[8])
                for row in rows
                if row[8] != PriceStatus.OK.value
            }
            # Le fournisseur et l'usine retenus sont relus ; les trois facteurs
            # du prix ne sont pas stockés. La décomposition complète se
            # recalcule à la demande (route /explain, tranche T2) plutôt que
            # d'être dupliquée en base, où elle finirait par diverger.
            explanations = {
                part_ref: PriceExplanation(
                    part_ref=part_ref,
                    unit_price=own_unit,
                    supplier_id=supplier_id,
                    plant_id=plant_id,
                )
                for part_ref, _, _, _, own_unit, _, supplier_id, plant_id, _ in rows
                if supplier_id is not None
            }

            cursor.execute(
                """
                SELECT system, cost, cost_share_pct
                FROM calculation_system_total
                WHERE calculation_id = %s
                ORDER BY system
                """,
                (calculation_id,),
            )
            systems = tuple(
                SystemTotal(system=system, cost=cost, share_pct=share)
                for system, cost, share in cursor.fetchall()
            )

            cursor.execute(
                """
                SELECT part_ref FROM calculation_issue
                WHERE calculation_id = %s AND kind = 'MISSING_PRICE'
                ORDER BY part_ref
                """,
                (calculation_id,),
            )
            missing = tuple(row[0] for row in cursor.fetchall())

        age = (finished_at - snapshot_taken_at) if snapshot_taken_at else timedelta(0)
        return Calculation(
            id=calculation_id,
            scenario_id=scenario_id,
            bom_version=bom_version,
            snapshot_id=snapshot_id,
            snapshot_age=age,
            snapshot_status=snapshot_status or "FRESH",
            engine_version=engine_version,
            rules_version=rules_version,
            active_rules=tuple(active_rules),
            display_currency=currency,
            status=CalculationStatus(status),
            total_cost=total,
            computed_at=finished_at,
            input_digest=digest,
            lines=lines,
            systems=systems,
            # Les contributeurs et la décomposition du prix se recalculent à la
            # lecture plutôt que d'être stockés en double : ce sont des vues du
            # même résultat, et une donnée dupliquée finit par diverger.
            # Les contributeurs sont une vue triée des mêmes lignes : ils se
            # reconstituent à la lecture, avec les libellés de la nomenclature.
            top_contributors=(),
            parts_without_price=missing,
            explanations=explanations,
            price_statuses=price_statuses,
        )
