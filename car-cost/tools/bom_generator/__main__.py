"""Génération du jeu de données de la Fiat Multipla 1.6 16V.

    python -m tools.bom_generator [--seeds-dir seeds] [--check]

`--check` régénère sans écrire et échoue si les fichiers présents diffèrent :
c'est la preuve du déterminisme, utilisable en intégration continue.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from . import graph, validation, writers
from .multipla import CONTROL_VALUES, build_multipla
from .pricing import SUPPLIERS, build_price_catalog, build_sourcing, reference_costing

BOM_VERSION_ID = "bom-multipla-2026-09-22"


def _format_report(report: dict, checksum: str) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("RAPPORT DE VALIDATION — nomenclature Fiat Multipla 1.6 16V")
    add("=" * 78)
    add("")
    add("Erreurs : 0")
    add("")
    add("-- Graphe " + "-" * 67)
    add(f"  pièces                      {report['parts']:>8}   (minimum exigé : 350)")
    add(f"    dont achetées             {report['purchased']:>8}")
    add(f"    dont fabriquées           {report['manufactured']:>8}")
    add(f"  arêtes                      {report['edges']:>8}")
    add(f"  profondeur maximale         {report['max_depth']:>8}   (minimum exigé : 5)")
    add(f"  pièces à parents multiples  {report['shared_parts']:>8}   (minimum exigé : 40)")
    add(f"  chemins racine → pièce      {report['total_paths']:>8}")
    add(f"  pièce la plus profonde      {report['deepest_part']}")
    add("  racine unique               oui")
    add("  acyclicité                  vérifiée par tri topologique")
    add("  orphelins                   0")
    add("  arêtes en double            0")
    add("")
    add("-- Coût de référence (scénario vide : fournisseur et usine par défaut) " + "-" * 7)
    add(f"  taux horaire                {report['costing']['labour_rate_eur_per_hour']:>12} EUR/h")
    add(f"  matière (pièces achetées)   {report['costing']['material_cost']:>12} EUR")
    add(f"  main-d'œuvre                {report['costing']['labour_cost']:>12} EUR")
    add(f"  TOTAL                       {report['costing']['total_cost']:>12} EUR")
    add(f"  CO2 procédé + matière       {report['costing']['own_co2']:>12} kg CO2e")
    add(f"  CO2 transport               {report['costing']['transport_co2']:>12} kg CO2e")
    add(f"  TOTAL CO2                   {report['costing']['total_co2']:>12} kg CO2e")
    add("")
    add("-- Valeurs de contrôle (vérifiables à la main) " + "-" * 31)
    add(f"  {'référence':<22} {'attendu':>9} {'calculé':>12}  emplois")
    for row in report["control_values"]:
        add(
            f"  {row['part_ref']:<22} {row['expected']:>9} "
            f"{row['computed']:>12}  {row['occurrence_count']:>5}   {row['label']}"
        )
    add("")
    add("-- Pièces les plus partagées " + "-" * 49)
    add(f"  {'référence':<22} {'parents':>7} {'emplois':>8} {'qté cumulée':>13}")
    for row in report["most_shared"][:12]:
        add(
            f"  {row['part_ref']:<22} {row['parent_count']:>7} "
            f"{row['occurrence_count']:>8} {row['cumulative_quantity']:>13} "
            f"{row['unit']}  {row['label']}"
        )
    add("")
    add("-- Coût par système " + "-" * 58)
    add(f"  {'système':<8} {'pièces':>7} {'coût EUR':>13} {'kg CO2e':>13}")
    for system, values in report["systems"].items():
        add(
            f"  {system:<8} {values['parts']:>7} {values['cost']:>13} "
            f"{values['co2']:>13}"
        )
    add("")
    add("-- Principaux contributeurs au coût " + "-" * 42)
    for row in report["top_contributors"][:10]:
        add(
            f"  {row['own_contribution']:>10} EUR  {row['part_ref']:<22} "
            f"×{row['cumulative_quantity']:<10} {row['label']}"
        )
    add("")
    add(f"empreinte du jeu de données : {checksum}")
    add("")
    add("Les prix, masses et facteurs carbone sont PLAUSIBLES MAIS SYNTHÉTIQUES.")
    add("=" * 78)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds-dir", default="seeds", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="ne rien écrire et échouer si les fichiers présents diffèrent",
    )
    args = parser.parse_args(argv)

    # La console Windows est en cp1252 par défaut : le rapport contient des
    # flèches et des symboles mathématiques qu'elle ne sait pas encoder.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    bom = build_multipla()
    cumulative = graph.cumulative_quantities(bom)
    mass = graph.rolled_up_mass(bom)
    sourcing = build_sourcing(bom)
    catalog = build_price_catalog(bom)
    costing = reference_costing(bom, cumulative, sourcing)

    errors = validation.validate(
        bom, cumulative, sourcing, catalog, costing, CONTROL_VALUES
    )
    if errors:
        print("RAPPORT DE VALIDATION — ÉCHEC", file=sys.stderr)
        print(f"Erreurs : {len(errors)}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    report = validation.build_report(bom, cumulative, costing, CONTROL_VALUES)

    if args.check:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            written = writers.write_all(
                Path(tmp), bom, BOM_VERSION_ID, cumulative, mass, sourcing,
                catalog, SUPPLIERS, report,
            )
            differences = []
            for name in written["files"]:
                candidate = (Path(tmp) / name).read_bytes()
                existing_path = args.seeds_dir / name
                if not existing_path.exists():
                    differences.append(f"{name} : absent du dépôt")
                elif existing_path.read_bytes() != candidate:
                    differences.append(f"{name} : diffère de la régénération")
        if differences:
            print("DÉTERMINISME — ÉCHEC", file=sys.stderr)
            for difference in differences:
                print(f"  - {difference}", file=sys.stderr)
            return 1
        print("Déterminisme vérifié : les fichiers régénérés sont identiques.")
        return 0

    written = writers.write_all(
        args.seeds_dir, bom, BOM_VERSION_ID, cumulative, mass, sourcing,
        catalog, SUPPLIERS, report,
    )
    print(_format_report(report, written["checksum"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
