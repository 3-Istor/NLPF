"""Lecture de la nomenclature en base.

SQL lit le graphe, le code applicatif calcule (ADR-0007). On ne trouvera donc
ici ni prix, ni multiplication de quantités, ni CTE récursive : trois requêtes
descriptives, et le graphe repart en objets de domaine.

Charger les ~474 pièces et ~689 arêtes d'un coup est assumé : le navigateur,
lui, ne reçoit que les enfants directs (ADR-0009). C'est le serveur qui tient le
graphe, et il coûte quelques millisecondes à le relire.
"""

from __future__ import annotations

from decimal import Decimal

from ...application.ports import (
    BomVersionNotFound,
    BomVersionNotValidated,
    BomVersionSummary,
)
from ...domain.bom import Bom, Edge, Part, ValuationMode
from .connection import PostgresRepository

VERSION_QUERY = """
    SELECT validated_at, root_part_ref
    FROM bom_version
    WHERE id = %s
"""

PARTS_QUERY = """
    SELECT part_ref, label, system, unit, valuation_mode, labour_minutes,
           mass_kg, carbon_factor_kg_co2e_per_unit
    FROM part
    WHERE bom_version_id = %s
    ORDER BY part_ref
"""

EDGES_QUERY = """
    SELECT parent_ref, child_ref, quantity
    FROM bom_edge
    WHERE bom_version_id = %s
    ORDER BY parent_ref, child_ref
"""


VERSIONS_QUERY = """
    SELECT id, label, root_part_ref, part_count, edge_count, validated_at,
           is_synthetic
    FROM bom_version
    ORDER BY created_at DESC, id
"""


class PostgresBomRepository(PostgresRepository):
    def load(self, version: str) -> Bom:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(VERSION_QUERY, (version,))
            row = cursor.fetchone()
            if row is None:
                raise BomVersionNotFound(version)
            validated_at, root_ref = row
            if validated_at is None:
                raise BomVersionNotValidated(version)

            cursor.execute(PARTS_QUERY, (version,))
            parts = {
                ref: Part(
                    ref=ref,
                    label=label,
                    system=system,
                    unit=unit,
                    valuation_mode=ValuationMode(mode),
                    carbon_factor=carbon,
                    labour_minutes=labour,
                    mass_kg=mass,
                )
                for ref, label, system, unit, mode, labour, mass, carbon
                in cursor.fetchall()
            }

            cursor.execute(EDGES_QUERY, (version,))
            edges = tuple(
                Edge(parent_ref=parent, child_ref=child, quantity=Decimal(quantity))
                for parent, child, quantity in cursor.fetchall()
            )

        return Bom(root_ref=root_ref, parts=parts, edges=edges)

    def versions(self) -> list[BomVersionSummary]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(VERSIONS_QUERY)
            return [BomVersionSummary(*row) for row in cursor.fetchall()]
