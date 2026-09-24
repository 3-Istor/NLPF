"""Sourcing, snapshots, scénarios et calculs en base.

Même règle que pour la nomenclature : SQL lit et écrit, le code applicatif
décide (ADR-0007). On ne trouvera ici ni multiplication de prix, ni sélection de
fournisseur par défaut — seulement des lignes rendues telles qu'elles sont.

Les écritures respectent ce que la base impose déjà par contraintes : un
snapshot et un calcul s'insèrent une fois, complets, et ne se modifient plus
(ADR-0003).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import psycopg

from ..application.ports import (
    CalculationNotFound,
    PriceSnapshotNotFound,
    QuarantineRecord,
    ScenarioNotFound,
)
from ..application.price_resolution import PriceExplanation
from ..application.run_calculation import Calculation, CalculationStatus, PriceStatus
from ..application.scenario import (
    Plant,
    Scenario,
    ScenarioParameter,
    Sourcing,
    SupplierOffer,
)
from ..domain.engine import PartLine
from ..domain.prices import PriceSnapshot


class _PostgresRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def _connect(self):
        return psycopg.connect(self.dsn)


# ---------------------------------------------------------------- sourcing


class PostgresSourcingRepository(_PostgresRepository):
    OFFERS = """
        SELECT ps.part_ref, ps.supplier_id, ps.price_multiplier, ps.is_default,
               s.name
        FROM part_supplier ps
        JOIN supplier s ON s.id = ps.supplier_id
        WHERE ps.bom_version_id = %s
        ORDER BY ps.part_ref, ps.supplier_id
    """
    PLANTS = """
        SELECT supplier_id, id, origin_country, price_coefficient,
               transport_co2_kg_per_kg, is_default, label, lead_time_days
        FROM supplier_plant
        ORDER BY supplier_id, id
    """

    def load(self, bom_version: str) -> Sourcing:
        offers: dict[str, list[SupplierOffer]] = {}
        plants: dict[str, list[Plant]] = {}

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self.OFFERS, (bom_version,))
            for part_ref, supplier_id, multiplier, is_default, name in (
                cursor.fetchall()
            ):
                offers.setdefault(part_ref, []).append(
                    SupplierOffer(supplier_id, multiplier, is_default, name)
                )

            cursor.execute(self.PLANTS)
            for (
                supplier_id, plant_id, origin, coefficient, co2, is_default,
                label, lead_time,
            ) in cursor.fetchall():
                plants.setdefault(supplier_id, []).append(
                    Plant(
                        plant_id, supplier_id, origin, coefficient, co2,
                        is_default, label, lead_time,
                    )
                )

        return Sourcing(
            offers={ref: tuple(rows) for ref, rows in offers.items()},
            plants={ref: tuple(rows) for ref, rows in plants.items()},
        )


# --------------------------------------------------------------- snapshots


class PostgresPriceSnapshotRepository(_PostgresRepository):
    """Un snapshot s'écrit une fois et ne se modifie jamais.

    Les prix y sont stockés **ramenés à l'unité** : la division par la quantité
    de référence du catalogue a eu lieu au moment de l'appel, et `price_per`
    vaut donc 1. Stocker le prix « par cent » ici obligerait chaque lecteur à
    refaire la division, et un seul oubli multiplierait par cent le coût de la
    visserie.
    """

    HEAD = """
        SELECT id, taken_at, source, status
        FROM price_snapshot
        {where}
        ORDER BY taken_at DESC
        LIMIT 1
    """
    LINES = """
        SELECT part_ref, price, currency, origin
        FROM price_snapshot_line
        WHERE snapshot_id = %s
        ORDER BY part_ref
    """
    QUARANTINED_REFS = """
        SELECT DISTINCT part_ref FROM price_quarantine WHERE snapshot_id = %s
    """

    def latest(self) -> PriceSnapshot | None:
        return self._read(None)

    def get(self, snapshot_id: str) -> PriceSnapshot:
        snapshot = self._read(snapshot_id)
        if snapshot is None:
            raise PriceSnapshotNotFound(snapshot_id)
        return snapshot

    def _read(self, snapshot_id: str | None) -> PriceSnapshot | None:
        where = "WHERE id = %s" if snapshot_id else ""
        parameters = (snapshot_id,) if snapshot_id else ()

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self.HEAD.format(where=where), parameters)
            head = cursor.fetchone()
            if head is None:
                return None
            identifier, taken_at, source, _status = head

            cursor.execute(self.LINES, (identifier,))
            rows = cursor.fetchall()

            cursor.execute(self.QUARANTINED_REFS, (identifier,))
            quarantined = frozenset(row[0] for row in cursor.fetchall())

        currency = rows[0][2] if rows else "EUR"
        # Sans l'origine, un snapshot dégradé relu en base passait pour frais,
        # et le calcul qui s'en servait sortait `OK` : un repli silencieux.
        # Les pièces restées sans prix, elles, ne se relisent pas — elles n'ont
        # pas de ligne ; le calcul les retrouve en cherchant leur prix.
        return PriceSnapshot(
            id=identifier,
            taken_at=taken_at,
            currency=currency,
            source=source,
            prices={part_ref: price for part_ref, price, _, _ in rows},
            fallback_refs=frozenset(
                part_ref for part_ref, _, _, origin in rows if origin == "FALLBACK"
            ),
            quarantined_refs=quarantined,
        )

    def save(self, snapshot: PriceSnapshot, quarantined=(), previous_id=None) -> None:
        """Écrit le snapshot et son journal de quarantaine, en une transaction.

        Une ligne de repli porte `origin = FALLBACK` et l'identifiant du
        snapshot dont elle vient : « d'où sort ce prix ? » doit avoir une
        réponse en base, pas seulement à l'écran.
        """
        counts = {
            "from_api": len(snapshot.prices) - len(snapshot.fallback_refs),
            "fallback": len(snapshot.fallback_refs),
            "quarantined": len(quarantined),
            "missing": len(snapshot.missing_refs),
        }
        degraded = snapshot.fallback_refs or snapshot.missing_refs

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO price_snapshot
                    (id, taken_at, source, status, counts, degraded_reason)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    snapshot.id,
                    snapshot.taken_at,
                    snapshot.source,
                    snapshot.status(datetime.now(timezone.utc)).value,
                    json.dumps(counts),
                    (
                        f"{counts['quarantined']} valeur(s) en quarantaine, "
                        f"{counts['fallback']} repli(s), "
                        f"{counts['missing']} sans prix"
                        if degraded
                        else None
                    ),
                ),
            )
            with cursor.copy(
                "COPY price_snapshot_line "
                "(snapshot_id, part_ref, currency, price, price_per, origin, as_of, "
                "fallback_from_snapshot_id) FROM STDIN"
            ) as copy:
                for part_ref, price in sorted(snapshot.prices.items()):
                    from_fallback = part_ref in snapshot.fallback_refs
                    copy.write_row(
                        (
                            snapshot.id,
                            part_ref,
                            snapshot.currency,
                            price,
                            Decimal(1),
                            "FALLBACK" if from_fallback else "API",
                            snapshot.taken_at,
                            previous_id if from_fallback else None,
                        )
                    )

            for entry in quarantined:
                cursor.execute(
                    """
                    INSERT INTO price_quarantine
                        (snapshot_id, part_ref, currency, rejected_value, reason,
                         replacement_price, replacement_from_snapshot_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        snapshot.id,
                        entry.part_ref,
                        snapshot.currency,
                        entry.rejected_value,
                        entry.reason,
                        entry.replacement,
                        previous_id if entry.replacement is not None else None,
                    ),
                )

    def quarantine_of(self, snapshot_id: str) -> list[QuarantineRecord]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM price_snapshot WHERE id = %s", (snapshot_id,))
            if cursor.fetchone() is None:
                raise PriceSnapshotNotFound(snapshot_id)

            cursor.execute(
                """
                SELECT part_ref, currency, rejected_value, reason, replacement_price,
                       replacement_from_snapshot_id, detected_at
                FROM price_quarantine
                WHERE snapshot_id = %s
                ORDER BY part_ref, id
                """,
                (snapshot_id,),
            )
            return [
                QuarantineRecord(
                    part_ref=part_ref,
                    currency=currency,
                    rejected_value=rejected,
                    reason=reason,
                    replacement=replacement,
                    replacement_from_snapshot=source_id,
                    detected_at=detected,
                )
                for (
                    part_ref, currency, rejected, reason, replacement, source_id,
                    detected,
                ) in cursor.fetchall()
            ]


# --------------------------------------------------------------- scénarios


class PostgresScenarioRepository(_PostgresRepository):
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
                    scenario.id,
                    scenario.display_currency,
                    scenario.labour_rate,
                    scenario.display_currency,
                    sorted(scenario.active_rules),
                ),
            )

    def get(self, scenario_id: str) -> Scenario:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT bom_version_id, display_currency, labour_rate, active_rules
                FROM scenario WHERE id = %s
                """,
                (scenario_id,),
            )
            head = cursor.fetchone()
            if head is None:
                raise ScenarioNotFound(scenario_id)
            bom_version, currency, labour_rate, active_rules = head

            cursor.execute(
                """
                SELECT part_ref, scope, path, supplier_id, plant_id, price_override,
                       price_override_justification, labour_minutes
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
                )
                for (
                    part_ref, scope, path, supplier_id, plant_id, override,
                    justification, labour_minutes,
                ) in cursor.fetchall()
            )

        return Scenario(
            id=scenario_id,
            bom_version=bom_version,
            display_currency=currency,
            labour_rate=labour_rate,
            active_rules=frozenset(active_rules),
            parameters=parameters,
        )

    def put_parameter(self, scenario_id: str, parameter: ScenarioParameter) -> str:
        import uuid

        identifier = f"prm-{uuid.uuid4().hex[:12]}"
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO scenario_parameter
                    (id, scenario_id, scope, part_ref, path, supplier_id, plant_id,
                     price_override, price_override_justification, labour_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (scenario_id, part_ref, coalesce(path, ''))
                DO UPDATE SET
                    scope = EXCLUDED.scope,
                    supplier_id = EXCLUDED.supplier_id,
                    plant_id = EXCLUDED.plant_id,
                    price_override = EXCLUDED.price_override,
                    price_override_justification =
                        EXCLUDED.price_override_justification,
                    labour_minutes = EXCLUDED.labour_minutes
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
                ),
            )
            return cursor.fetchone()[0]

    def delete_parameter(self, scenario_id: str, parameter_id: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM scenario_parameter WHERE scenario_id = %s AND id = %s",
                (scenario_id, parameter_id),
            )


# ----------------------------------------------------------------- calculs


class PostgresCalculationRepository(_PostgresRepository):
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
        from datetime import timedelta

        from ..application.run_calculation import Contributor, SystemTotal

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
