"""Qui peut fournir quoi, et depuis quelles usines (ADR-0010).

SQL lit les offres telles qu'elles sont ; choisir le fournisseur par défaut
est une décision de la couche application (ADR-0007).
"""

from __future__ import annotations

from ...application.scenario import Plant, Sourcing, SupplierOffer
from .connection import PostgresRepository


class PostgresSourcingRepository(PostgresRepository):
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
