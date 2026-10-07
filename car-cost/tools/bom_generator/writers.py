"""Écriture des fichiers du jeu de données.

Déterminisme : aucun horodatage d'exécution, aucun parcours d'ensemble non
trié, fins de ligne forcées à « \\n » quelle que soit la plateforme. Deux
exécutions doivent produire des fichiers identiques au bit près.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from decimal import Decimal
from pathlib import Path

from .densities import DENSITIES_KG_M3
from .model import Bom

DATASET_DATE = "2026-09-22"
GENERATOR_VERSION = "1.0.0"

DISCLAIMER = (
    "Prix, masses, facteurs carbone, coefficients d'usine et délais sont "
    "PLAUSIBLES MAIS SYNTHÉTIQUES. Ils ont été construits pour être cohérents "
    "entre eux et d'ordres de grandeur crédibles. Ils ne proviennent d'aucun "
    "constructeur, d'aucun fournisseur et d'aucune base de données publique, et "
    "ne doivent jamais être présentés comme des données réelles."
)

CONVENTIONS = {
    "valuation_mode": (
        "purchased : le coût est le prix d'achat, la pièce est une feuille. "
        "manufactured : le coût est la somme des enfants plus la main-d'œuvre, "
        "et la pièce n'a pas de prix propre (ADR-0008)."
    ),
    "carbon_factor": (
        "Émissions PROPRES par unité : empreinte de l'extraction à la sortie "
        "d'usine pour une pièce achetée, émissions du seul procédé d'assemblage "
        "pour un ensemble fabriqué. Les enfants ne sont jamais inclus."
    ),
    "unit_price": (
        "prix de référence ÷ price_per × multiplicateur fournisseur × "
        "coefficient d'usine (ADR-0010)."
    ),
    "transport_co2": (
        "kg CO2e par kilogramme de pièce transportée jusqu'au site "
        "d'assemblage (Turin, IT). Intensité, pas forfait."
    ),
    "expected_cumulative_quantity": (
        "Quantité nécessaire pour un véhicule : somme sur tous les chemins des "
        "produits de quantités. Valeur de contrôle du moteur, calculée par deux "
        "algorithmes indépendants."
    ),
    "decimals": "Échelle 6 partout, aucun arrondi dans les données (ADR-0011).",
}


#: Ce qui distingue un jeu de données d'un autre dans les fichiers écrits. Le
#: Multipla est la valeur par défaut : ses fichiers ne changent pas d'un octet
#: quand un autre véhicule passe par les mêmes writers.
MULTIPLA = {
    "slug": "multipla-16v",
    "vehicle": "Fiat Multipla 1.6 16V",
    "bom_file": "bom_multipla.json",
    "dataset_date": DATASET_DATE,
    "generator_version": GENERATOR_VERSION,
    "assembly_site": "IT",
    "transport_co2": CONVENTIONS["transport_co2"],
    "currencies": ["EUR", "USD", "RUB"],
    "extra_conventions": {},
    #: Densités des matières au kilogramme, en kg/m³ (ADR-0017). Un jeu qui ne
    #: déclare pas cette clé n'écrit pas la colonne `density_kg_m3` : les
    #: fichiers des autres véhicules restent identiques à l'octet.
    "densities": DENSITIES_KG_M3,
}


def _dumps(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _part_row(
    bom_version: str,
    ref: str,
    part,
    cumulative: dict[str, Decimal],
    mass,
    densities: dict[str, Decimal] | None = None,
):
    row = {
        "bom_version_id": bom_version,
        "part_ref": ref,
        "label": part.label,
        "category": part.category,
        "system": part.system,
        "unit": part.unit,
        "valuation_mode": part.valuation_mode,
        "labour_minutes": "" if part.labour_minutes is None else str(part.labour_minutes),
        "base_price_eur": "" if part.base_price_eur is None else str(part.base_price_eur),
        "price_per": str(part.price_per),
        "material_ref": part.material_ref or "",
        "mass_kg": str(mass[ref]),
        "carbon_factor_kg_co2e_per_unit": str(part.carbon_factor),
        "expected_cumulative_quantity": str(cumulative[ref]),
    }
    if densities is not None:
        if ref in densities and part.unit != "kg":
            raise ValueError(f"{ref} : une densité n'a de sens que pour une matière au kg")
        row["density_kg_m3"] = str(densities[ref]) if ref in densities else ""
    return row


def _csv(rows: list[dict], fieldnames: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_all(
    seeds_dir: Path,
    bom: Bom,
    bom_version: str,
    cumulative: dict[str, Decimal],
    mass: dict[str, Decimal],
    sourcing: dict[str, list[dict]],
    catalog: dict[str, dict],
    suppliers: tuple[dict, ...],
    report: dict,
    dataset: dict = MULTIPLA,
) -> dict[str, str]:
    conventions = {
        **CONVENTIONS,
        "transport_co2": dataset["transport_co2"],
        **dataset["extra_conventions"],
    }
    part_rows = [
        _part_row(bom_version, ref, part, cumulative, mass, dataset.get("densities"))
        for ref, part in bom.parts.items()
    ]
    edge_rows = [
        {
            "bom_version_id": bom_version,
            "parent_ref": edge.parent_ref,
            "child_ref": edge.child_ref,
            "parent_valuation_mode": bom.parts[edge.parent_ref].valuation_mode,
            "quantity": str(edge.quantity),
            "unit": edge.unit,
            "after_sales_quantity": str(edge.after_sales),
        }
        for edge in bom.edges
    ]

    canonical = _dumps({"parts": part_rows, "edges": edge_rows})
    checksum = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    bom_document = {
        "metadata": {
            "dataset": f"bom-{dataset['slug']}",
            "bom_version_id": bom_version,
            "vehicle": dataset["vehicle"],
            "root_part_ref": bom.root_ref,
            "dataset_date": dataset["dataset_date"],
            "generator_version": dataset["generator_version"],
            "is_synthetic": True,
            "disclaimer": DISCLAIMER,
            "reference_currency": "EUR",
            "assembly_site": dataset["assembly_site"],
            "labour_rate_eur_per_hour": report["costing"]["labour_rate_eur_per_hour"],
            "conventions": conventions,
            "seed_checksum": checksum,
            "counts": {
                "parts": report["parts"],
                "edges": report["edges"],
                "purchased": report["purchased"],
                "manufactured": report["manufactured"],
                "shared_parts": report["shared_parts"],
                "max_depth": report["max_depth"],
            },
        },
        "parts": part_rows,
        "edges": edge_rows,
    }

    supplier_document = {
        "metadata": {
            "dataset": f"suppliers-{dataset['slug']}",
            "bom_version_id": bom_version,
            "dataset_date": dataset["dataset_date"],
            "is_synthetic": True,
            "disclaimer": DISCLAIMER,
            "assembly_site": dataset["assembly_site"],
            "conventions": {
                "price_multiplier": "Porté par le fournisseur (marge, qualité, service).",
                "plant_price_coefficient": "Porté par le site : coût local de production.",
                "transport_co2_kg_per_kg": conventions["transport_co2"],
                "independence": (
                    "Fournisseur et site sont deux leviers indépendants : on peut "
                    "changer de site sans changer de fournisseur (ADR-0010)."
                ),
            },
        },
        "suppliers": [
            {
                "supplier_id": supplier["id"],
                "name": supplier["name"],
                "family": supplier["family"],
                "home_country": supplier["home_country"],
                "plants": [
                    {
                        "plant_id": plant["id"],
                        "label": plant["label"],
                        "origin_country": plant["origin"],
                        "price_coefficient": plant["coef"],
                        "lead_time_days": plant["lead"],
                        "transport_co2_kg_per_kg": plant["co2"],
                        "is_default": plant["default"],
                    }
                    for plant in supplier["plants"]
                ],
            }
            for supplier in suppliers
        ],
        "part_suppliers": [
            {
                "part_ref": ref,
                "supplier_id": offer["supplier_id"],
                "price_multiplier": str(offer["price_multiplier"]),
                "is_default": offer["is_default"],
            }
            for ref in sorted(sourcing)
            for offer in sourcing[ref]
        ],
    }

    catalog_document = {
        "metadata": {
            "dataset": f"price-catalog-{dataset['slug']}",
            "bom_version_id": bom_version,
            "dataset_date": dataset["dataset_date"],
            "is_synthetic": True,
            "disclaimer": DISCLAIMER,
            "currencies": dataset["currencies"],
            "conventions": {
                "independent_currencies": (
                    "Les trois devises sont des prix indépendants, pas la "
                    "conversion d'un prix pivot : aucun taux de change n'est lu "
                    "à l'exécution (ADR-0003)."
                ),
                "year_min_max": (
                    "Bornes que le prix parcourt sur l'année simulée par l'API "
                    "de prix (indices de marché × drivers)."
                ),
                "drivers": (
                    "Exposition du prix aux indices de marché simulés : facteur "
                    "= 1 + Σ poids × variation de l'indice."
                ),
                "price_per": "Le prix s'entend pour price_per unités (la visserie s'achète par 100).",
            },
        },
        "prices": {ref: catalog[ref] for ref in sorted(catalog)},
    }

    files = {
        dataset["bom_file"]: _dumps(bom_document),
        "parts.csv": _csv(part_rows, list(part_rows[0].keys())),
        "edges.csv": _csv(edge_rows, list(edge_rows[0].keys())),
        "price_catalog.json": _dumps(catalog_document),
        "suppliers.json": _dumps(supplier_document),
        "validation_report.json": _dumps(report),
    }
    for name, content in files.items():
        _write(seeds_dir / name, content)

    return {"checksum": checksum, "files": sorted(files)}
