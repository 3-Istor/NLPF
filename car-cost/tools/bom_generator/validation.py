"""Contrôles du jeu de données et rapport de validation.

Une erreur ici fait échouer la génération : un fichier non conforme ne doit pas
exister, parce qu'un moteur développé contre lui serait à reprendre.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from . import graph
from .model import MANUFACTURED, PURCHASED, Bom

MIN_PARTS = 350
MIN_DEPTH = 5
MIN_SHARED_PARTS = 40
MIN_SUPPLIERS_PER_PART = 2


def validate(
    bom: Bom,
    cumulative: dict[str, Decimal],
    sourcing: dict[str, list[dict]],
    catalog: dict[str, dict],
    costing: dict,
    control_values: dict[str, str],
    *,
    require_volume: bool = True,
    min_suppliers: int = MIN_SUPPLIERS_PER_PART,
    currencies: tuple[str, ...] = ("EUR", "USD", "RUB"),
) -> list[str]:
    """`require_volume` porte les minimums du sujet (taille, profondeur,
    partage) : ils valent pour le Multipla généré, pas pour une nomenclature
    importée telle qu'un constructeur la fournit."""
    errors: list[str] = []

    # -- structure ----------------------------------------------------------
    found_roots = graph.roots(bom)
    if found_roots != [bom.root_ref]:
        errors.append(f"racine non unique : {found_roots}")

    for ref in graph.orphans(bom):
        errors.append(f"pièce orpheline, employée nulle part : {ref}")

    try:
        graph.topological_order(bom)
    except Exception as exc:  # noqa: BLE001 - le message porte le diagnostic
        errors.append(f"acyclicité : {exc}")
        return errors  # sans ordre topologique, le reste n'a pas de sens

    seen_edges = Counter((e.parent_ref, e.child_ref) for e in bom.edges)
    for pair, count in seen_edges.items():
        if count > 1:
            errors.append(f"arête en double : {pair[0]} → {pair[1]} ({count} fois)")

    # -- volumétrie exigée --------------------------------------------------
    if require_volume and len(bom.parts) < MIN_PARTS:
        errors.append(f"{len(bom.parts)} pièces, minimum attendu {MIN_PARTS}")

    depth = graph.max_depth(bom)
    if require_volume and depth < MIN_DEPTH:
        errors.append(f"profondeur {depth}, minimum attendu {MIN_DEPTH}")

    parents = graph.parents_index(bom)
    shared = [ref for ref in bom.parts if len(set(parents.get(ref, []))) >= 2]
    if require_volume and len(shared) < MIN_SHARED_PARTS:
        errors.append(
            f"{len(shared)} pièces à parents multiples, minimum attendu "
            f"{MIN_SHARED_PARTS} — sans elles la nomenclature est un arbre déguisé"
        )

    # -- valorisation (ADR-0008) -------------------------------------------
    children = graph.children_index(bom)
    for ref, part in bom.parts.items():
        if part.valuation_mode == PURCHASED:
            if children.get(ref):
                errors.append(f"{ref} : pièce achetée avec des enfants")
            if part.base_price_eur is None:
                errors.append(f"{ref} : pièce achetée sans prix")
            if part.mass_kg is None:
                errors.append(f"{ref} : pièce achetée sans masse (CO2 de transport)")
        elif part.valuation_mode == MANUFACTURED:
            if not children.get(ref):
                errors.append(f"{ref} : ensemble fabriqué sans enfant")
            if part.base_price_eur is not None:
                errors.append(f"{ref} : ensemble fabriqué avec un prix propre")
            if part.labour_minutes is None:
                errors.append(f"{ref} : ensemble fabriqué sans main-d'œuvre")
        else:
            errors.append(f"{ref} : mode de valorisation inconnu {part.valuation_mode}")

        if part.carbon_factor < 0:
            errors.append(f"{ref} : facteur carbone négatif")

    # -- quantités cumulées : deux algorithmes, un seul résultat ------------
    try:
        by_enumeration = graph.cumulative_quantities_by_enumeration(bom)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"énumération des chemins : {exc}")
        by_enumeration = {}

    for ref, expected in by_enumeration.items():
        if cumulative[ref] != expected:
            errors.append(
                f"{ref} : quantité cumulée {cumulative[ref]} par programmation "
                f"dynamique contre {expected} par énumération des chemins"
            )

    # -- valeurs de contrôle vérifiables à la main -------------------------
    for ref, expected_str in control_values.items():
        if ref not in bom.parts:
            errors.append(f"valeur de contrôle sur une référence inconnue : {ref}")
            continue
        expected = Decimal(expected_str)
        if cumulative[ref] != expected:
            errors.append(
                f"{ref} : quantité cumulée {cumulative[ref]}, valeur de contrôle "
                f"attendue {expected}"
            )

    # -- conservation (I1) --------------------------------------------------
    total_own = sum(
        (values["own_contribution"] for values in costing["per_part"].values()),
        Decimal(0),
    )
    if total_own != costing["total_cost"]:
        errors.append(
            f"somme des contributions propres {total_own} ≠ total "
            f"{costing['total_cost']}"
        )
    if costing["root_full_cost"] != costing["total_cost"]:
        errors.append(
            f"coût unitaire complet de la racine {costing['root_full_cost']} ≠ "
            f"total des contributions {costing['total_cost']}"
        )
    if costing["root_full_co2"] != costing["total_co2"]:
        errors.append(
            f"CO2 complet de la racine {costing['root_full_co2']} ≠ total "
            f"{costing['total_co2']}"
        )

    # -- sourcing et catalogue ---------------------------------------------
    for ref, part in bom.parts.items():
        if part.valuation_mode != PURCHASED:
            continue
        offers = sourcing.get(ref, [])
        if len(offers) < min_suppliers:
            errors.append(
                f"{ref} : {len(offers)} fournisseur(s), minimum {min_suppliers}"
            )
        if sum(1 for offer in offers if offer["is_default"]) != 1:
            errors.append(f"{ref} : il faut exactement un fournisseur par défaut")
        entry = catalog.get(ref)
        if entry is None:
            errors.append(f"{ref} : absente du catalogue de prix")
            continue
        for code in currencies:
            if code not in entry["prices"]:
                errors.append(f"{ref} : pas de prix en {code}")
                continue
            prices = entry["prices"][code]
            low = Decimal(prices["year_min"])
            high = Decimal(prices["year_max"])
            reference = Decimal(prices["reference"])
            if not (low <= reference <= high):
                errors.append(
                    f"{ref} ({code}) : référence {reference} hors de [{low}, {high}]"
                )

    return errors


def build_report(
    bom: Bom,
    cumulative: dict[str, Decimal],
    costing: dict,
    control_values: dict[str, str],
) -> dict:
    parents = graph.parents_index(bom)
    counts = graph.path_counts(bom)
    depths = graph.depth_of(bom)

    shared = sorted(
        (
            {
                "part_ref": ref,
                "label": bom.parts[ref].label,
                "parent_count": len(set(parents.get(ref, []))),
                "occurrence_count": counts[ref],
                "cumulative_quantity": str(cumulative[ref]),
                "unit": bom.parts[ref].unit,
            }
            for ref in bom.parts
            if len(set(parents.get(ref, []))) >= 2
        ),
        key=lambda row: (-row["parent_count"], row["part_ref"]),
    )

    by_system: dict[str, dict[str, Decimal]] = {}
    for ref, part in bom.parts.items():
        bucket = by_system.setdefault(
            part.system, {"cost": Decimal(0), "co2": Decimal(0), "parts": Decimal(0)}
        )
        bucket["cost"] += costing["per_part"][ref]["own_contribution"]
        bucket["co2"] += costing["per_part"][ref]["own_co2_contribution"]
        bucket["parts"] += 1

    contributors = sorted(
        (
            {
                "part_ref": ref,
                "label": bom.parts[ref].label,
                "system": bom.parts[ref].system,
                "cumulative_quantity": str(cumulative[ref]),
                "own_contribution": str(
                    costing["per_part"][ref]["own_contribution"].quantize(
                        Decimal("0.01")
                    )
                ),
            }
            for ref in bom.parts
        ),
        key=lambda row: (-Decimal(row["own_contribution"]), row["part_ref"]),
    )

    return {
        "parts": len(bom.parts),
        "edges": len(bom.edges),
        "purchased": sum(
            1 for p in bom.parts.values() if p.valuation_mode == PURCHASED
        ),
        "manufactured": sum(
            1 for p in bom.parts.values() if p.valuation_mode == MANUFACTURED
        ),
        "max_depth": graph.max_depth(bom),
        "deepest_part": max(depths, key=lambda ref: (depths[ref], ref)),
        "shared_parts": len(shared),
        "total_paths": sum(counts.values()),
        "most_shared": shared[:15],
        "systems": {
            system: {
                "parts": int(values["parts"]),
                "cost": str(values["cost"].quantize(Decimal("0.01"))),
                "co2": str(values["co2"].quantize(Decimal("0.01"))),
            }
            for system, values in sorted(by_system.items())
        },
        "top_contributors": contributors[:15],
        "control_values": [
            {
                "part_ref": ref,
                "label": bom.parts[ref].label,
                "expected": expected,
                "computed": str(cumulative[ref]),
                "occurrence_count": counts[ref],
            }
            for ref, expected in control_values.items()
        ],
        "costing": {
            "labour_rate_eur_per_hour": str(costing["labour_rate"]),
            "material_cost": str(costing["material_cost"].quantize(Decimal("0.01"))),
            "labour_cost": str(costing["labour_cost"].quantize(Decimal("0.01"))),
            "total_cost": str(costing["total_cost"].quantize(Decimal("0.01"))),
            "total_cost_exact": str(costing["total_cost"]),
            "own_co2": str(costing["own_co2"].quantize(Decimal("0.01"))),
            "transport_co2": str(costing["transport_co2"].quantize(Decimal("0.01"))),
            "total_co2": str(costing["total_co2"].quantize(Decimal("0.01"))),
        },
    }
