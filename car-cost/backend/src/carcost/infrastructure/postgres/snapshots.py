"""Snapshots de prix et journal de quarantaine en base.

Un snapshot s'insère une fois, complet, et ne se modifie plus : la base le
refuse par déclencheur (ADR-0003).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from ...application.ports import PriceSnapshotNotFound, QuarantineRecord
from ...domain.prices import PriceSnapshot
from .connection import PostgresRepository


class PostgresPriceSnapshotRepository(PostgresRepository):
    """Un snapshot s'écrit une fois et ne se modifie jamais.

    Les prix y sont stockés **ramenés à l'unité** : la division par la quantité
    de référence du catalogue a eu lieu au moment de l'appel, et `price_per`
    vaut donc 1. Stocker le prix « par cent » ici obligerait chaque lecteur à
    refaire la division, et un seul oubli multiplierait par cent le coût de la
    visserie.
    """

    HEAD = """
        SELECT id, taken_at, source, status, bom_version_id
        FROM price_snapshot
        {where}
        ORDER BY bom_version_id IS NULL, taken_at DESC
        LIMIT 1
    """
    #: Les snapshots de la nomenclature, puis ceux d'avant la migration 0006
    #: qui ne disaient pas pour quelle nomenclature ils étaient pris.
    FOR_BOM = "WHERE bom_version_id = %s OR bom_version_id IS NULL"
    LINES = """
        SELECT part_ref, price, currency, origin
        FROM price_snapshot_line
        WHERE snapshot_id = %s
        ORDER BY part_ref
    """
    QUARANTINED_REFS = """
        SELECT DISTINCT part_ref FROM price_quarantine WHERE snapshot_id = %s
    """

    def latest(self, bom_version: str | None = None) -> PriceSnapshot | None:
        return self._read(None, bom_version)

    def list_all(self, bom_version: str | None = None) -> tuple[PriceSnapshot, ...]:
        where = self.FOR_BOM if bom_version else ""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id
                FROM price_snapshot
                {where}
                ORDER BY taken_at DESC, id DESC
                """,
                (bom_version,) if bom_version else (),
            )
            identifiers = tuple(row[0] for row in cursor.fetchall())
        return tuple(self.get(identifier) for identifier in identifiers)

    def get(self, snapshot_id: str) -> PriceSnapshot:
        snapshot = self._read(snapshot_id)
        if snapshot is None:
            raise PriceSnapshotNotFound(snapshot_id)
        return snapshot

    def _read(
        self, snapshot_id: str | None, bom_version: str | None = None
    ) -> PriceSnapshot | None:
        if snapshot_id:
            where, parameters = "WHERE id = %s", (snapshot_id,)
        elif bom_version:
            where, parameters = self.FOR_BOM, (bom_version,)
        else:
            where, parameters = "", ()

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self.HEAD.format(where=where), parameters)
            head = cursor.fetchone()
            if head is None:
                return None
            identifier, taken_at, source, _status, head_bom_version = head

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
            bom_version=head_bom_version,
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
                    (id, taken_at, source, status, counts, degraded_reason,
                     bom_version_id)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
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
                    snapshot.bom_version,
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
