"""Chargement du jeu de données en base.

Le chargeur **n'ouvre pas de connexion** : il émet sur sa sortie standard le
script que `psql` exécutera. Trois conséquences, toutes voulues :

  - il se teste sans base, donc le contrôle d'intégrité se teste sans base ;
  - le chargement reste un vrai `COPY`, pas une boucle d'INSERT ;
  - aucune dépendance : bibliothèque standard seule, et le domaine pour valider.

Ce qui vient d'ici ne franchit jamais la frontière : le domaine ignore que ce
module existe (ADR-0004).
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from ..domain.bom import Bom, Edge, Part, ValuationMode
from ..domain.bom_validation import validate_bom


class SeedRejected(Exception):
    """Le jeu de données viole une règle : rien ne doit entrer en base."""


PART_COLUMNS = (
    "bom_version_id",
    "part_ref",
    "label",
    "category",
    "system",
    "unit",
    "valuation_mode",
    "labour_minutes",
    "base_price_eur",
    "price_per",
    "material_ref",
    "mass_kg",
    "density_kg_m3",
    "carbon_factor_kg_co2e_per_unit",
    "expected_cumulative_quantity",
)

EDGE_COLUMNS = (
    "bom_version_id",
    "parent_ref",
    "child_ref",
    "parent_valuation_mode",
    "quantity",
    "unit",
    "after_sales_quantity",
)


def build_load_script(
    *,
    metadata: Mapping,
    parts: Sequence[Mapping],
    edges: Sequence[Mapping],
    suppliers: Mapping,
) -> str:
    """Valide d'abord, émet ensuite. Un fichier refusé ne produit aucun SQL."""
    # Un fichier antérieur au SAV n'a pas la colonne : aucune pièce de rechange.
    edges = [
        {**row, "after_sales_quantity": row.get("after_sales_quantity") or "0"}
        for row in edges
    ]
    bom = _to_domain(metadata, parts, edges)
    _reject_if_invalid(bom, parts)

    version = metadata["bom_version_id"]
    blocks = [
        "BEGIN;",
        "",
        _insert_bom_version(metadata, parts, edges),
        "",
        _copy_block("part", PART_COLUMNS, parts),
        "",
        _copy_block("bom_edge", EDGE_COLUMNS, edges),
    ]

    supplier_sql = _supplier_blocks(version, suppliers)
    if supplier_sql:
        blocks += ["", supplier_sql]

    blocks += [
        "",
        "-- Intégrité vérifiée au chargement : acyclicité par tri topologique,",
        "-- racine unique, aucun orphelin, quantités cumulées conformes.",
        "UPDATE bom_version SET validated_at = now(), validation_report = "
        f"{_quote(_report(bom, parts))}::jsonb WHERE id = {_quote(version)};",
        "",
        "COMMIT;",
        "",
    ]
    return "\n".join(blocks)


# --------------------------------------------------------------------- domaine


def _to_domain(
    metadata: Mapping, parts: Sequence[Mapping], edges: Sequence[Mapping]
) -> Bom:
    domain_parts = {
        row["part_ref"]: Part(
            ref=row["part_ref"],
            label=row["label"],
            system=row["system"],
            unit=row["unit"],
            valuation_mode=ValuationMode(row["valuation_mode"]),
            carbon_factor=Decimal(row["carbon_factor_kg_co2e_per_unit"]),
            labour_minutes=(
                Decimal(row["labour_minutes"]) if row["labour_minutes"] else None
            ),
            mass_kg=Decimal(row["mass_kg"]) if row["mass_kg"] else None,
            material_ref=row.get("material_ref") or None,
            density_kg_m3=(
                Decimal(row["density_kg_m3"]) if row.get("density_kg_m3") else None
            ),
        )
        for row in parts
    }
    domain_edges = tuple(
        Edge(
            row["parent_ref"],
            row["child_ref"],
            Decimal(row["quantity"]),
            Decimal(row.get("after_sales_quantity") or 0),
        )
        for row in edges
    )
    try:
        return Bom(
            root_ref=metadata["root_part_ref"], parts=domain_parts, edges=domain_edges
        )
    except ValueError as unusable:
        raise SeedRejected(str(unusable)) from unusable


def _reject_if_invalid(bom: Bom, parts: Sequence[Mapping]) -> None:
    faults = [violation.message for violation in validate_bom(bom)]
    faults += _price_faults(parts)
    if faults:
        raise SeedRejected(
            f"{len(faults)} violation(s) : " + " ; ".join(faults[:20])
        )
    _reject_if_quantities_disagree(bom, bom.topological_order(), parts)


def _price_faults(parts: Sequence[Mapping]) -> list[str]:
    """Le prix n'est pas une donnée de la pièce dans le domaine : c'est ici,
    à l'entrée du catalogue, qu'on vérifie la face « prix » de l'ADR-0008."""
    faults = []
    for row in parts:
        purchased = row["valuation_mode"] == ValuationMode.PURCHASED.value
        if purchased and not row["base_price_eur"]:
            faults.append(f"{row['part_ref']} est achetée et n'a pas de prix")
        if not purchased and row["base_price_eur"]:
            faults.append(
                f"{row['part_ref']} est fabriquée et porte un prix propre : son "
                f"contenu serait perdu"
            )
    return faults


def _reject_if_quantities_disagree(
    bom: Bom, order: tuple[str, ...], parts: Sequence[Mapping]
) -> None:
    """Le fichier annonce une quantité cumulée ; on la recalcule et on compare.

    Ce n'est pas redondant avec le générateur : à l'import, rien ne garantit que
    le fichier vient de lui.
    """
    cumulative = {ref: Decimal(0) for ref in bom.parts}
    cumulative[bom.root_ref] = Decimal(1)
    for ref in order:
        for child_ref, quantity in bom.children_of(ref):
            cumulative[child_ref] += cumulative[ref] * quantity

    for row in parts:
        announced = Decimal(row["expected_cumulative_quantity"])
        computed = cumulative[row["part_ref"]]
        if announced != computed:
            raise SeedRejected(
                f"{row['part_ref']} : quantité cumulée annoncée {announced}, "
                f"recalculée {computed}"
            )


def _report(bom: Bom, parts: Sequence[Mapping]) -> str:
    purchased = sum(
        1 for row in parts if row["valuation_mode"] == ValuationMode.PURCHASED.value
    )
    return json.dumps(
        {
            "checks": [
                "acyclicite_par_tri_topologique",
                "racine_unique",
                "aucun_orphelin",
                "valorisation_exclusive",
                "quantites_cumulees_recalculees",
            ],
            "parts": len(parts),
            "purchased": purchased,
            "manufactured": len(parts) - purchased,
            "edges": len(bom.edges),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


# ------------------------------------------------------------------------- SQL


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _copy_field(value) -> str:
    """Format texte de COPY : la chaîne vide est NULL, le reste est échappé.

    Sans l'échappement, une tabulation dans un libellé décalerait toutes les
    colonnes suivantes sans qu'aucune erreur ne soit levée.
    """
    if value is None or value == "":
        return "\\N"
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _copy_block(table: str, columns: Sequence[str], rows: Sequence[Mapping]) -> str:
    lines = [f"COPY {table} ({', '.join(columns)}) FROM STDIN;"]
    # `get` : un jeu qui ne déclare pas de densités (les Valhalla) n'a pas la
    # colonne ; elle se charge alors à NULL. Les autres colonnes restent exigées.
    optional = {"density_kg_m3"}
    lines += [
        "\t".join(
            _copy_field(row.get(column) if column in optional else row[column])
            for column in columns
        )
        for row in rows
    ]
    lines.append("\\.")
    return "\n".join(lines)


def _insert_bom_version(
    metadata: Mapping, parts: Sequence[Mapping], edges: Sequence[Mapping]
) -> str:
    return (
        "INSERT INTO bom_version (id, label, root_part_ref, generator_version, "
        "seed_checksum, is_synthetic, part_count, edge_count, "
        "reference_labour_rate) VALUES ("
        f"{_quote(metadata['bom_version_id'])}, "
        f"{_quote(metadata['vehicle'])}, "
        f"{_quote(metadata['root_part_ref'])}, "
        f"{_quote(metadata['generator_version'])}, "
        f"{_quote(metadata['seed_checksum'])}, "
        f"{'true' if metadata['is_synthetic'] else 'false'}, "
        f"{len(parts)}, {len(edges)}, "
        f"{_labour_rate(metadata)});"
    )


def _labour_rate(metadata: Mapping) -> str:
    rate = metadata.get("labour_rate_eur_per_hour")
    if rate is None:
        return "NULL"
    # Un nombre, pas du texte cité : refuser ici ce qui ne se lit pas comme tel
    # plutôt que de laisser psql échouer au milieu de la transaction.
    return str(Decimal(str(rate)))


def _supplier_blocks(version: str, suppliers: Mapping) -> str:
    declared = suppliers.get("suppliers") or []
    links = suppliers.get("part_suppliers") or []
    if not declared:
        return ""

    supplier_rows = [
        [s["supplier_id"], s["name"], s["home_country"]] for s in declared
    ]
    plant_rows = [
        [
            plant["plant_id"],
            s["supplier_id"],
            plant["label"],
            plant["origin_country"],
            plant["price_coefficient"],
            plant["lead_time_days"],
            plant["transport_co2_kg_per_kg"],
            "true" if plant["is_default"] else "false",
        ]
        for s in declared
        for plant in s["plants"]
    ]
    link_rows = [
        [
            version,
            link["part_ref"],
            "purchased",
            link["supplier_id"],
            link["price_multiplier"],
            "true" if link["is_default"] else "false",
        ]
        for link in links
    ]

    def block(table: str, columns: str, rows: list[list]) -> str:
        lines = [f"COPY {table} ({columns}) FROM STDIN;"]
        lines += ["\t".join(_copy_field(value) for value in row) for row in rows]
        lines.append("\\.")
        return "\n".join(lines)

    def shared(table: str, columns: str, rows: list[list]) -> str:
        """Un fournisseur sert plusieurs nomenclatures (les trois Valhalla) :
        le deuxième chargement le retrouve en base et ne le réécrit pas."""
        staging = f"{table}_seed"
        return "\n".join(
            [
                f"CREATE TEMP TABLE {staging} (LIKE {table} INCLUDING DEFAULTS) "
                "ON COMMIT DROP;",
                block(staging, columns, rows),
                f"INSERT INTO {table} ({columns}) SELECT {columns} FROM {staging} "
                "ON CONFLICT (id) DO NOTHING;",
            ]
        )

    return "\n\n".join(
        [
            shared("supplier", "id, name, home_country", supplier_rows),
            shared(
                "supplier_plant",
                "id, supplier_id, label, origin_country, price_coefficient, "
                "lead_time_days, transport_co2_kg_per_kg, is_default",
                plant_rows,
            ),
            block(
                "part_supplier",
                "bom_version_id, part_ref, part_valuation_mode, supplier_id, "
                "price_multiplier, is_default",
                link_rows,
            ),
        ]
    )


# ------------------------------------------------------------------- lecture


def seed_directories(root: Path) -> list[Path]:
    """Le Multipla à la racine de `seeds/`, puis chaque Valhalla.

    L'ordre est fixe : la première nomenclature chargée est celle que l'écran
    ouvre par défaut.
    """
    nested = sorted(
        path.parent for path in (root / "valhalla").glob("*/bom_*.json")
    )
    return [root, *nested]


def read_seeds(seeds_dir: Path) -> dict:
    candidates = sorted(seeds_dir.glob("bom_*.json"))
    if len(candidates) != 1:
        raise SeedRejected(
            f"{seeds_dir} : un seul fichier bom_*.json attendu, "
            f"{len(candidates)} trouvé(s)"
        )
    bom = json.loads(candidates[0].read_text(encoding="utf-8"))
    suppliers = json.loads((seeds_dir / "suppliers.json").read_text(encoding="utf-8"))
    return {
        "metadata": bom["metadata"],
        "parts": list(csv.DictReader(_lines(seeds_dir / "parts.csv"))),
        "edges": list(csv.DictReader(_lines(seeds_dir / "edges.csv"))),
        "suppliers": suppliers,
    }


def seed_bom(seeds_dir: Path) -> Bom:
    """Le graphe d'un jeu de données, tel que le domaine le lit.

    Même construction que le chargement en base : les tests et les cas d'usage
    qui veulent la vraie nomenclature n'ont pas besoin de Postgres.
    """
    seeds = read_seeds(seeds_dir)
    edges = [
        {**row, "after_sales_quantity": row.get("after_sales_quantity") or "0"}
        for row in seeds["edges"]
    ]
    return _to_domain(seeds["metadata"], seeds["parts"], edges)


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()
