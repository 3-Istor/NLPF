"""Import des trois Aston Martin Valhalla dans le format du jeu de données.

    python -m tools.valhalla_import [--seeds-dir seeds] [--check]

Lit `seeds/valhalla/source/*.json` (les fichiers fournis, gardés comme entrée)
et écrit, par variante, **les mêmes fichiers que le Multipla** dans
`seeds/valhalla/<variante>/` : le chargeur les lit sans cas particulier.

La nomenclature source est un arbre de catégories. Elle devient un graphe à
trois ou quatre niveaux : véhicule → catégorie (ensemble fabriqué) → [sous-
catégorie de la motorisation] → lignes achetées.

Seules les fixations sont regroupées. Le fichier en fait une ligne par
interface (« vis_boulon_structurel — Monocoque -> sous-cadre »), toutes sous
une catégorie « fixations ». Comme sur le Multipla, chaque type devient une
pièce, montée sous chaque ensemble qui l'utilise avec la quantité de ses
interfaces (`FASTENER_GROUPS`). C'est le seul partage du graphe : on ne
fabrique pas celui qui n'existe pas dans le fichier.

`--check` régénère sans écrire et échoue si les fichiers présents diffèrent.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from tools.bom_generator import graph, validation, writers
from tools.bom_generator.model import BomBuilder, dec
from tools.bom_generator.price_drivers import (
    classify,
    daily_factors,
    fx_ratios,
    load_indices,
    weights,
)
from tools.bom_generator.pricing import EUR_TO_RUB, EUR_TO_USD, _spread, reference_costing

from . import enrich
from .suppliers import ALL_SUPPLIERS, ASSEMBLY_SITE, SOURCE_SUPPLIERS, offers_for

DATASET_DATE = "2026-10-05"
GENERATOR_VERSION = "valhalla-import-1.0.0"
# Atelier britannique, synthétique. Un taux de 60 garde le coût de la minute
# exact (1 EUR) : un taux qui ne divise pas 60 produit des décimales infinies
# et casse la conservation au dernier chiffre.
LABOUR_RATE_EUR_PER_HOUR = Decimal("60.00")
SCALE6 = Decimal("0.000001")


@dataclass(frozen=True)
class Variant:
    key: str
    source: str
    prefix: str
    root: str
    vehicle: str
    #: Masse à sec visée, en kg. L'hybride reprend l'ordre de grandeur annoncé
    #: publiquement ; les deux autres variantes sont hypothétiques.
    target_mass_kg: Decimal
    #: Coût de référence visé, rapporté à celui de l'hybride. None : les prix
    #: du fichier source tels quels (l'hybride, la seule variante réelle).
    target_cost_ratio: Decimal | None = None

    @property
    def bom_version(self) -> str:
        return f"bom-valhalla-{self.key}-{DATASET_DATE}"


VARIANTS = (
    Variant("hybride", "aston_martin_valhalla_hybride_phev.json", "VALH",
            "VEH-VALHALLA-HYB", "Aston Martin Valhalla — hybride rechargeable (PHEV)",
            Decimal("1655")),
    Variant("thermique", "aston_martin_valhalla_thermique.json", "VALT",
            "VEH-VALHALLA-THE", "Aston Martin Valhalla — thermique V8 (hypothétique)",
            Decimal("1540"), Decimal("0.95")),
    Variant("electrique", "aston_martin_valhalla_electrique.json", "VALE",
            "VEH-VALHALLA-ELE", "Aston Martin Valhalla — électrique 800 V (hypothétique)",
            Decimal("1960"), Decimal("1.05")),
)

# clé de catégorie → (système, catégorie, libellé). Systèmes et catégories sont
# ceux du Multipla : la décomposition de la synthèse marche telle quelle.
CATEGORIES: dict[str, tuple[str, str, str]] = {
    "configuration_vehicule": ("VEH", "vehicle", "Configuration véhicule"),
    "structure_carrosserie": ("CAR", "body", "Structure et carrosserie"),
    "aerodynamique_exterieur": ("CAR", "body", "Aérodynamique et extérieur"),
    "vitrage_eclairage": ("CAR", "glazing", "Vitrage et éclairage"),
    "habitacle_securite": ("INT", "interior", "Habitacle et sécurité"),
    "chassis_suspension": ("CHS", "chassis", "Châssis et suspension"),
    "direction": ("CHS", "chassis", "Direction"),
    "freinage": ("CHS", "chassis", "Freinage"),
    "roues_pneus": ("CHS", "chassis", "Roues et pneumatiques"),
    "electrique_basse_tension": ("ELE", "electrical", "Électricité basse tension"),
    "electronique_adas": ("ELE", "electrical", "Électronique et ADAS"),
    "hvac": ("INT", "interior", "Climatisation et chauffage"),
    "hydraulique_actif": ("CHS", "chassis", "Hydraulique active"),
    "auxiliaires": ("ELE", "electrical", "Auxiliaires"),
    "consommables": ("FLU", "fluid", "Consommables et fluides"),
    "fixations": ("FIX", "fastener", "Fixations"),
    "motorisation": ("GMP", "engine", "Motorisation"),
    "thermique_essence": ("GMP", "engine", "Moteur thermique V8"),
    "hybride_electrique_hv": ("GMP", "engine", "Chaîne électrique haute tension"),
    "carburant_essence": ("GMP", "engine", "Alimentation carburant"),
    "echappement": ("GMP", "engine", "Échappement"),
    "gestion_thermique": ("GMP", "engine", "Gestion thermique"),
    "transmission": ("TRN", "transmission", "Transmission"),
}

#: L'ensemble où se monte chaque interface de fixation, par plage d'identifiants
#: `FAST-`. Les fichiers source rangent toutes les vis sous « fixations », une
#: ligne par interface ; les identifiants sont communs aux trois variantes, qui
#: n'ajoutent que leurs propres plages (201+ thermique, 301+ électrique).
FASTENER_GROUPS: tuple[tuple[int, int, str], ...] = (
    (1, 28, "structure_carrosserie"),
    (29, 39, "aerodynamique_exterieur"),
    (40, 59, "chassis_suspension"),
    (60, 60, "direction"),
    (61, 70, "chassis_suspension"),
    (71, 83, "freinage"),
    (84, 88, "roues_pneus"),
    (89, 105, "thermique_essence"),
    (106, 113, "transmission"),
    (114, 130, "hybride_electrique_hv"),
    (131, 136, "gestion_thermique"),
    (137, 140, "echappement"),
    # Écrans thermiques -> structure : l'électrique en porte aussi, sans
    # échappement. Ils se vissent sur la structure.
    (141, 141, "structure_carrosserie"),
    (142, 142, "echappement"),
    (143, 152, "habitacle_securite"),
    (153, 154, "electrique_basse_tension"),
    (155, 158, "electronique_adas"),
    (159, 160, "vitrage_eclairage"),
    (161, 162, "electrique_basse_tension"),
    (163, 167, "hvac"),
    (168, 172, "hydraulique_actif"),
    (201, 203, "thermique_essence"),
    (204, 205, "transmission"),
    (301, 304, "hybride_electrique_hv"),
    (305, 306, "transmission"),
    (307, 307, "hybride_electrique_hv"),
    (308, 309, "gestion_thermique"),
)
FASTENERS = "fixations"

UNITS = {"piece": "pce", "unit": "pce", "assembly": "pce", "zone": "pce", "set": "jeu"}

DISCLAIMER_NOTE = (
    "Lignes, prix et fournisseurs principaux viennent des fichiers Valhalla "
    "fournis, eux-mêmes synthétiques. Masses, facteurs carbone, temps "
    "d'assemblage, usines, délais et fournisseurs alternatifs sont générés ici."
)


def _ref(variant: Variant, source_id: str) -> str:
    return f"{variant.prefix}-{source_id}"


def _assembly_ref(variant: Variant, key: str) -> str:
    return f"{variant.prefix}-CAT-{key.upper().replace('_', '-')}"


def _fastener_group(source_id: str) -> str:
    number = int(source_id.removeprefix("FAST-"))
    for low, high, key in FASTENER_GROUPS:
        if low <= number <= high:
            return key
    raise SystemExit(f"{source_id} : aucun ensemble connu pour cette fixation")


def _fastener_type(row: dict) -> str:
    """`vis_boulon_structurel — Monocoque -> sous-cadre` → `vis_boulon_structurel`."""
    return row["nom"].split(" — ", 1)[0]


def _pooled_price(rows: list[dict]) -> Decimal:
    """Le prix le plus fréquent d'un fournisseur pour un type ; à égalité, le plus bas."""
    prices = [dec(row["prix_unitaire"]["prix_eur"]) for row in rows]
    return min(set(prices), key=lambda price: (-prices.count(price), price))


def _fastener_lines(
    variant: Variant, rows: list[dict], groups: set[str]
) -> tuple[list[dict], dict[str, dict[str, Decimal]], dict[str, int]]:
    """Une pièce par type de fixation, montée sous chaque ensemble qui l'utilise.

    Sur le Multipla, une vis M6 est une pièce, portée par neuf ensembles avec
    une quantité par arête. Les fichiers Valhalla en font une ligne par
    interface, toutes sous « fixations » : aucune pièce n'y a deux parents.

    Renvoie les lignes (format de `build_variant`), les arêtes par ensemble
    et, par ensemble, le nombre d'interfaces qu'il reçoit : le temps de
    vissage suit la vis.
    """
    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(_fastener_type(row), []).append(row)

    lines: list[dict] = []
    edges: dict[str, dict[str, Decimal]] = {}
    interfaces: dict[str, int] = {}
    for kind, members in sorted(by_type.items()):
        ref = f"{variant.prefix}-FIX-{kind.upper().replace('_', '-')}"
        by_supplier: dict[str, list[dict]] = {}
        for row in members:
            by_supplier.setdefault(row["fournisseur"]["nom"], []).append(row)
        # Le fournisseur retenu est celui de la majorité des interfaces ; les
        # autres deviennent des offres, au rapport de leur prix (ADR-0010).
        default = min(
            by_supplier, key=lambda name: (-len(by_supplier[name]), _pooled_price(by_supplier[name]))
        )
        reference = _pooled_price(by_supplier[default])
        # Une ligne réelle à ce prix : sa devise d'origine reste cohérente.
        source = next(
            row for row in by_supplier[default]
            if dec(row["prix_unitaire"]["prix_eur"]) == reference
        )
        row = {**source, "nom": kind.replace("_", " ").capitalize(), "quantite_sav": 0}
        for member in members:
            key = _fastener_group(member["id"])
            if key not in groups:
                raise SystemExit(
                    f"{variant.key} : {member['id']} se monte sous {key}, absent de la variante"
                )
            target = edges.setdefault(key, {})
            target[ref] = target.get(ref, Decimal(0)) + dec(member["quantite"])
            interfaces[key] = interfaces.get(key, 0) + 1
        lines.append({
            "ref": ref, "row": row, "category_key": FASTENERS,
            "quantity": sum((dec(m["quantite"]) for m in members), Decimal(0)),
            "extra_offers": {
                name: (_pooled_price(rows_) / reference).quantize(SCALE6)
                for name, rows_ in sorted(by_supplier.items()) if name != default
            },
        })
    return lines, edges, interfaces


def _groups(categories: dict) -> list[tuple[str, str | None, list[dict]]]:
    """(catégorie, sous-catégorie, lignes), sous-catégories vides écartées."""
    groups = []
    for key, content in categories.items():
        if isinstance(content, dict):
            for sub_key, rows in content.items():
                if rows:
                    groups.append((key, sub_key, rows))
        elif content:
            groups.append((key, None, content))
    return groups


def _profiles(row: dict, category: str) -> tuple[str, str, str]:
    """(profil de prix, profil physique, réservoir de fournisseurs)."""
    price_profile = classify(row["nom"], row["description"])
    if category == "fixations":
        return price_profile, "fastener", "fastener"
    if row["unite"] in ("L", "kg", "g") or category == "consommables":
        return price_profile, "fluid", "fluid"
    return price_profile, price_profile, price_profile


#: La seule catégorie dont les prix sont recalés : celle qui distingue les
#: variantes. Structure, châssis, habitacle… gardent le prix du fichier source.
CALIBRATED = "motorisation"


def _calibrate(document: dict, factor: Decimal) -> None:
    """Met à l'échelle les prix de la motorisation, dans les deux devises.

    Arrondi au centime comme le fichier source : le coût obtenu tombe à
    quelques euros de la cible, ce qui suffit pour un écart « de l'ordre de ».
    """
    for rows in document["categories"][CALIBRATED].values():
        for row in rows:
            for price in (row["prix_unitaire"], row["prix_final"]):
                for key in ("prix", "prix_eur"):
                    price[key] = (price[key] * factor).quantize(Decimal("0.01"))


def _calibrated_part(document: dict) -> Decimal:
    """Ce que la motorisation pèse dans le coût de référence : quantité montée
    × prix, le fournisseur source étant retenu à multiplicateur et usine 1."""
    return sum(
        (
            dec(row["quantite"]) * row["prix_unitaire"]["prix_eur"]
            for rows in document["categories"][CALIBRATED].values()
            for row in rows
        ),
        Decimal(0),
    )


def build_variant(
    variant: Variant, source_dir: Path, indices: dict,
    motor_factor: Decimal = Decimal(1),
) -> dict:
    document = json.loads(
        (source_dir / variant.source).read_text(encoding="utf-8"), parse_float=Decimal
    )
    if motor_factor != 1:
        _calibrate(document, motor_factor)
    groups = [g for g in _groups(document["categories"]) if g[0] != FASTENERS]
    fastener_rows = [
        row for category, _, rows in _groups(document["categories"])
        if category == FASTENERS for row in rows
    ]
    fasteners, fastener_edges, fastener_interfaces = _fastener_lines(
        variant, fastener_rows, {sub or category for category, sub, _ in groups}
    )

    # -- les lignes achetées, avec leur masse brute ---------------------------
    # (ligne source, ensemble parent ou None pour une vis partagée, catégorie, réf, quantité)
    sources = [
        (row, sub or category, category, _ref(variant, row["id"]), dec(row["quantite"]))
        for category, sub, rows in groups for row in rows
    ] + [(f["row"], None, FASTENERS, f["ref"], f["quantity"]) for f in fasteners]
    extra_offers = {f["ref"]: f["extra_offers"] for f in fasteners}
    lines: list[dict] = []
    for row, group, category, ref, quantity in sources:
        system, part_category, _ = CATEGORIES[group or category]
        unit = UNITS.get(row["unite"], row["unite"])
        price_profile, physical, pool = _profiles(row, category)
        mass, anchored = enrich.unit_mass(ref, row["nom"], row["unite"], physical, quantity)
        lines.append({
            "ref": ref, "row": row, "group": group, "system": system,
            "category": part_category, "unit": unit, "price_profile": price_profile,
            "physical": physical, "pool": pool, "mass": mass, "anchored": anchored,
            "quantity": quantity,
        })

    masses, factor = enrich.scale_masses(lines, variant.target_mass_kg)

    # -- la nomenclature -------------------------------------------------------
    b = BomBuilder()
    for line in lines:
        row = line["row"]
        b.purchased(
            line["ref"], row["nom"], system=line["system"], category=line["category"],
            unit=line["unit"], price=str(dec(row["prix_unitaire"]["prix_eur"]).quantize(SCALE6)),
            carbon=str(enrich.carbon_factor(line["ref"], masses[line["ref"]], line["physical"])),
            mass=str(masses[line["ref"]]),
        )

    by_group: dict[str, list[dict]] = {}
    for line in lines:
        if line["group"] is not None:
            by_group.setdefault(line["group"], []).append(line)

    root_children: dict[str, int] = {}
    engine_children: dict[str, int] = {}
    for category, sub, _ in groups:
        key = sub or category
        system, part_category, label = CATEGORIES[key]
        members = by_group[key]
        screws = fastener_edges.get(key, {})
        b.assembly(
            _assembly_ref(variant, key), label, system=system, category=part_category,
            labour=enrich.labour_minutes(
                key, len(members) + fastener_interfaces.get(key, 0)
            ),
            children={
                **{l["ref"]: str(l["quantity"]) for l in members},
                **{ref: str(quantity) for ref, quantity in sorted(screws.items())},
            },
            after_sales={
                l["ref"]: str(dec(l["row"]["quantite_sav"])) for l in members
                if l["row"]["quantite_sav"]
            },
        )
        if sub:
            engine_children[_assembly_ref(variant, sub)] = 1
        else:
            root_children[_assembly_ref(variant, category)] = 1

    if engine_children:
        b.assembly(
            _assembly_ref(variant, "motorisation"), CATEGORIES["motorisation"][2],
            system="GMP", category="engine",
            labour=enrich.labour_minutes("motorisation", len(engine_children)),
            children=engine_children,
        )
        root_children[_assembly_ref(variant, "motorisation")] = 1

    b.assembly(
        variant.root, f"{variant.vehicle} — véhicule complet", system="VEH",
        category="vehicle", labour=enrich.FINAL_ASSEMBLY_MINUTES, children=root_children,
    )
    bom = b.build(variant.root)

    # -- sourcing et catalogue -------------------------------------------------
    sourcing = {
        line["ref"]: _with_source_offers(
            offers_for(line["ref"], line["row"]["fournisseur"]["nom"], line["pool"]),
            extra_offers.get(line["ref"], {}),
        )
        for line in lines
    }
    catalog = {line["ref"]: _catalog_entry(line, indices) for line in lines}

    return {
        "bom": bom, "sourcing": sourcing, "catalog": catalog, "mass_factor": factor,
        "calibrated_part": _calibrated_part(document),
    }


def _with_source_offers(offers: list[dict], extra: dict[str, Decimal]) -> list[dict]:
    """Ajoute les autres fournisseurs du fichier source d'une vis partagée, à
    leur multiplicateur réel ; il remplace un alternatif tiré au hasard."""
    for name, multiplier in extra.items():
        supplier_id = SOURCE_SUPPLIERS[name]["id"]
        offers = [o for o in offers if o["supplier_id"] != supplier_id]
        offers.append(
            {"supplier_id": supplier_id, "price_multiplier": multiplier, "is_default": False}
        )
    return offers


def _bounds(reference: Decimal, factors: list[Decimal]) -> dict[str, str]:
    series = [reference * f for f in factors]
    return {
        "reference": str(reference.quantize(SCALE6)),
        "year_min": str(min(series).quantize(SCALE6)),
        "year_max": str(max(series).quantize(SCALE6)),
    }


def _catalog_entry(line: dict, indices: dict) -> dict:
    """Prix de référence dans quatre devises, et ce qui les fait bouger.

    Le fournisseur source facture en GBP ou en EUR. Son prix dans sa devise ne
    suit que les matières ; l'autre devise suit en plus le cours GBP/EUR
    simulé. USD et RUB restent des prix indépendants, comme pour le Multipla.
    """
    row, ref = line["row"], line["ref"]
    origin = row["fournisseur"]["devise"]
    drivers = weights(line["price_profile"])
    factors = daily_factors(drivers, indices)
    fx = fx_ratios(indices)
    eur = dec(row["prix_unitaire"]["prix_eur"])
    if origin == "GBP":
        gbp = dec(row["prix_unitaire"]["prix"])
        eur_factors = [f * r for f, r in zip(factors, fx)]
        gbp_factors = factors
    else:
        gbp = eur / indices["GBP_EUR"][0]
        eur_factors = factors
        gbp_factors = [f / r for f, r in zip(factors, fx)]
    return {
        "unit": line["unit"],
        "price_per": "1",
        "origin_currency": origin,
        "profile": line["price_profile"],
        "drivers": drivers,
        "prices": {
            "EUR": _bounds(eur, eur_factors),
            "GBP": _bounds(gbp, gbp_factors),
            "USD": _bounds(eur * EUR_TO_USD * _spread(ref, "usd", "0.970000", "1.030000"), factors),
            "RUB": _bounds(eur * EUR_TO_RUB * _spread(ref, "rub", "0.950000", "1.050000"), factors),
        },
    }


def dataset_for(variant: Variant) -> dict:
    return {
        "slug": f"valhalla-{variant.key}",
        "vehicle": variant.vehicle,
        "bom_file": f"bom_valhalla_{variant.key}.json",
        "dataset_date": DATASET_DATE,
        "generator_version": GENERATOR_VERSION,
        "assembly_site": ASSEMBLY_SITE,
        "transport_co2": (
            "kg CO2e par kilogramme de pièce transportée jusqu'au site "
            "d'assemblage (Gaydon, GB). Intensité, pas forfait."
        ),
        "currencies": ["EUR", "GBP", "USD", "RUB"],
        "extra_conventions": {
            "provenance": DISCLAIMER_NOTE,
            "after_sales_quantity": (
                "Pièces de rechange livrées avec le véhicule (SAV). Portées par "
                "l'arête, hors quantité montée : elles n'entrent dans le calcul "
                "que si le scénario active le SAV."
            ),
            "calibration": (
                "Thermique et électrique sont hypothétiques : les prix de leur "
                "motorisation sont mis à l'échelle pour que leur coût de "
                "référence se tienne à ±5 % de celui de l'hybride (thermique "
                "0,95, électrique 1,05). Le facteur appliqué est dans "
                "validation_report.json (calibration). Les autres pièces gardent "
                "le prix du fichier source."
            ),
            "drivers": (
                "Exposition du prix aux indices de marché simulés : facteur = "
                "1 + Σ poids × variation. Le change GBP/EUR s'applique en plus "
                "selon origin_currency."
            ),
        },
    }


def _costing(built: dict) -> dict:
    bom = built["bom"]
    return reference_costing(
        bom, graph.cumulative_quantities(bom), built["sourcing"], ALL_SUPPLIERS,
        LABOUR_RATE_EUR_PER_HOUR,
    )


def motor_factor_for(
    variant: Variant, source_dir: Path, indices: dict, reference_cost: Decimal | None
) -> Decimal:
    """Le facteur qui amène le coût de la variante à sa cible.

    Le coût est affine en ce facteur : seule la motorisation bouge, le reste
    (pièces communes, main-d'œuvre) est fixe. Un calcul suffit, sans
    tâtonnement : facteur = 1 + (cible − coût actuel) / part de la motorisation.
    """
    if variant.target_cost_ratio is None or reference_cost is None:
        return Decimal(1)
    built = build_variant(variant, source_dir, indices)
    current = _costing(built)["total_cost"]
    target = reference_cost * variant.target_cost_ratio
    factor = 1 + (target - current) / built["calibrated_part"]
    if factor <= 0:
        raise SystemExit(f"{variant.key} : cible de coût inatteignable (facteur {factor})")
    return factor.quantize(Decimal("0.0001"))


def generate(
    variant: Variant, source_dir: Path, indices: dict, out_dir: Path,
    reference_cost: Decimal | None = None,
) -> dict:
    factor = motor_factor_for(variant, source_dir, indices, reference_cost)
    built = build_variant(variant, source_dir, indices, factor)
    bom = built["bom"]
    cumulative = graph.cumulative_quantities(bom)
    mass = graph.rolled_up_mass(bom)
    costing = _costing(built)
    errors = validation.validate(
        bom, cumulative, built["sourcing"], built["catalog"], costing, {},
        require_volume=False, currencies=("EUR", "GBP", "USD", "RUB"),
    )
    if errors:
        raise SystemExit(
            f"{variant.key} : {len(errors)} erreur(s)\n  - " + "\n  - ".join(errors[:20])
        )
    report = validation.build_report(bom, cumulative, costing, {})
    report["mass"] = {
        "vehicle_kg": str(mass[bom.root_ref].quantize(Decimal("0.1"))),
        "target_kg": str(variant.target_mass_kg),
        "free_mass_scale": str(built["mass_factor"]),
    }
    report["calibration"] = {
        "category": CALIBRATED,
        "price_factor": str(factor),
        "target_cost_ratio_to_hybrid": (
            str(variant.target_cost_ratio) if variant.target_cost_ratio else None
        ),
    }
    used = {offer["supplier_id"] for offers in built["sourcing"].values() for offer in offers}
    suppliers = tuple(s for s in ALL_SUPPLIERS if s["id"] in used)
    written = writers.write_all(
        out_dir, bom, variant.bom_version, cumulative, mass, built["sourcing"],
        built["catalog"], suppliers, report, dataset_for(variant),
    )
    return {
        "report": report, "files": written["files"], "total_cost": costing["total_cost"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds-dir", default="seeds", type=Path)
    parser.add_argument("--indices", default="price-api/data/price_indices.json", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    source_dir = args.seeds_dir / "valhalla" / "source"
    indices = load_indices(args.indices)
    differences: list[str] = []
    # L'hybride d'abord : son coût est la référence des deux autres.
    reference_cost: Decimal | None = None
    for variant in VARIANTS:
        target = args.seeds_dir / "valhalla" / variant.key
        if args.check:
            with tempfile.TemporaryDirectory() as tmp:
                result = generate(variant, source_dir, indices, Path(tmp), reference_cost)
                reference_cost = reference_cost or result["total_cost"]
                for name in result["files"]:
                    existing = target / name
                    if not existing.exists():
                        differences.append(f"{variant.key}/{name} : absent du dépôt")
                    elif existing.read_bytes() != (Path(tmp) / name).read_bytes():
                        differences.append(f"{variant.key}/{name} : diffère de la régénération")
            continue
        result = generate(variant, source_dir, indices, target, reference_cost)
        reference_cost = reference_cost or result["total_cost"]
        report = result["report"]
        print(
            f"{variant.key:<11} {report['parts']:>4} pièces  {report['edges']:>4} arêtes  "
            f"coût {report['costing']['total_cost']:>12} EUR  "
            f"CO2 {report['costing']['total_co2']:>10} kg  "
            f"masse {report['mass']['vehicle_kg']} kg (échelle {report['mass']['free_mass_scale']})  "
            f"main-d'œuvre {report['costing']['labour_cost']} EUR  "
            f"motorisation ×{report['calibration']['price_factor']}"
        )
    if args.check:
        if differences:
            print("DÉTERMINISME — ÉCHEC", file=sys.stderr)
            for difference in differences:
                print(f"  - {difference}", file=sys.stderr)
            return 1
        print("Déterminisme vérifié : les trois Valhalla régénérées sont identiques.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
