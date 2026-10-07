"""Écriture d'une variante de carrosserie : tout dans une transaction, ou rien (ADR-0017 §6).

Les requêtes copient, insèrent et filtrent. Quantités cumulées, masses et
validation viennent du `VariantPlan` : aucun calcul ici. Les prix, densités et
la maquette sont synthétiques.
"""

from __future__ import annotations

import json

from ...application.ports import NewVariant, VariantIdCollision
from .connection import PostgresRepository

PARENT_PARTS = """
    SELECT part_ref, label, category, system, unit, valuation_mode, labour_minutes,
           base_price_eur, price_per, material_ref, mass_kg, density_kg_m3,
           carbon_factor_kg_co2e_per_unit
    FROM part WHERE bom_version_id = %s
"""
INSERT_PART = """
    INSERT INTO part (bom_version_id, part_ref, label, category, system, unit,
        valuation_mode, labour_minutes, base_price_eur, price_per, material_ref,
        mass_kg, density_kg_m3, carbon_factor_kg_co2e_per_unit,
        expected_cumulative_quantity)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
PARENT_EDGES = "SELECT parent_ref, child_ref, unit, after_sales_quantity FROM bom_edge WHERE bom_version_id = %s"
INSERT_EDGE = """
    INSERT INTO bom_edge (bom_version_id, parent_ref, child_ref, parent_valuation_mode,
        quantity, unit, after_sales_quantity)
    VALUES (%s, %s, %s, 'manufactured', %s, %s, %s)
"""
# Une version qui existe déjà garde sa ligne : la concurrente attend la
# validation de la première (clé primaire), puis ne fait rien.
INSERT_VERSION = """
    INSERT INTO bom_version (id, label, root_part_ref, generator_version, seed_checksum,
        is_synthetic, part_count, edge_count, reference_labour_rate, parent_version_id)
    SELECT %s, %s, %s, %s, %s, true, %s, %s, reference_labour_rate, id
    FROM bom_version WHERE id = %s
    ON CONFLICT (id) DO NOTHING
    RETURNING id
"""
COPY_OFFERS = """
    INSERT INTO part_supplier (bom_version_id, part_ref, part_valuation_mode, supplier_id,
        price_multiplier, is_default)
    SELECT %s, part_ref, part_valuation_mode, supplier_id, price_multiplier, is_default
    FROM part_supplier WHERE bom_version_id = %s
"""


class PostgresVariantWriter(PostgresRepository):
    def save_variant(self, variant: NewVariant) -> None:
        plan, parent = variant.plan, variant.parent_id
        # `with connection` : COMMIT à la sortie normale, ROLLBACK si une exception sort.
        with self._connect() as connection:
            created = connection.execute(
                INSERT_VERSION,
                (variant.id, variant.label, plan.bom.root_ref, variant.generator_version,
                 f"sha256:{variant.sha256}", len(plan.bom.parts), len(plan.bom.edges), parent),
            ).fetchone()
            if created is None:
                # Déjà écrite, par un import simultané du même fichier ou plus tôt.
                known = connection.execute(
                    "SELECT sha256 FROM bom_model WHERE bom_version_id = %s", (variant.id,)
                ).fetchone()
                if known is None or known[0] != variant.sha256:
                    raise VariantIdCollision(variant.id)
                return

            with connection.cursor() as cursor:
                cursor.execute(PARENT_PARTS, (parent,))
                rows = {row[0]: list(row) for row in cursor.fetchall()}
                for ref, (material, mass) in plan.updated_parts.items():
                    rows[ref][9], rows[ref][10] = material, mass
                for new in plan.new_parts:
                    rows[new.ref] = [
                        new.ref, new.label, new.category, new.system, new.unit, "manufactured",
                        new.labour_minutes, None, 1, new.material_ref, new.mass_kg, None,
                        new.carbon_factor,
                    ]
                cursor.executemany(
                    INSERT_PART,
                    [(variant.id, *row, plan.cumulative[ref]) for ref, row in rows.items()],
                )

                cursor.execute(PARENT_EDGES, (parent,))
                known_edges = {(p, c): (unit, sav) for p, c, unit, sav in cursor.fetchall()}
                cursor.executemany(
                    INSERT_EDGE,
                    [
                        (variant.id, e.parent_ref, e.child_ref, e.quantity,
                         *known_edges.get((e.parent_ref, e.child_ref),
                                          (plan.bom.parts[e.child_ref].unit, 0)))
                        for e in plan.bom.edges
                    ],
                )
                cursor.execute(COPY_OFFERS, (variant.id, parent))

                purchased = sum(part.is_purchased for part in plan.bom.parts.values())
                report = {
                    "checks": [
                        "acyclicite_par_tri_topologique", "racine_unique", "aucun_orphelin",
                        "valorisation_exclusive", "quantites_cumulees_recalculees",
                    ],
                    "parts": len(plan.bom.parts),
                    "purchased": purchased,
                    "manufactured": len(plan.bom.parts) - purchased,
                    "edges": len(plan.bom.edges),
                }
                cursor.execute(
                    "UPDATE bom_version SET validated_at = now(), validation_report = %s::jsonb"
                    " WHERE id = %s",
                    (json.dumps(report, sort_keys=True), variant.id),
                )
                cursor.execute(
                    "INSERT INTO bom_model (bom_version_id, glb, sha256, source)"
                    " VALUES (%s, %s, %s, 'imported')",
                    (variant.id, variant.glb, variant.sha256),
                )
