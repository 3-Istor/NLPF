"""Fournisseurs, usines, catalogue de prix et coût de référence.

Tous les chiffres produits ici sont **synthétiques**. Ils sont construits pour
être cohérents entre eux — une usine lointaine et bon marché porte un
coefficient inférieur à 1 et un transport plus émetteur (ADR-0010) — et pour
être **déterministes** : ils dérivent d'une empreinte SHA-256 de la référence,
jamais d'un tirage aléatoire.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from .model import PURCHASED, Bom, dec

# Taux de conversion synthétiques, figés, servant UNIQUEMENT à fabriquer le
# catalogue. L'application ne les relit jamais : les trois devises sont des prix
# indépendants (ADR-0003).
EUR_TO_USD = Decimal("1.08")
EUR_TO_RUB = Decimal("98.50")

# Taux horaire de référence, en euros. Donnée du scénario, pas une règle.
REFERENCE_LABOUR_RATE = Decimal("42.00")

ASSEMBLY_SITE = "IT"  # Turin : le site d'assemblage auquel les usines livrent.

# --------------------------------------------------------------------------
# Fournisseurs et usines
#
# `transport_co2_kg_per_kg` : kg de CO2e par kilogramme de pièce transportée
# jusqu'au site d'assemblage. C'est une intensité, pas un forfait : le CO2 de
# transport d'un bloc-cylindres n'est pas celui d'une vis.
# --------------------------------------------------------------------------

SUPPLIERS: tuple[dict, ...] = (
    # -- matières premières
    {"id": "SUP-METALLI", "name": "Metalli Padani", "family": "RAW", "home_country": "IT",
     "plants": (
         {"id": "PLT-METALLI-IT", "label": "Brescia", "origin": "IT", "coef": "1.000000", "lead": 9, "co2": "0.018000", "default": True},
         {"id": "PLT-METALLI-PL", "label": "Katowice", "origin": "PL", "coef": "0.948000", "lead": 19, "co2": "0.052000", "default": False},
     )},
    {"id": "SUP-EUROPOLY", "name": "Europoly Kunststoffe", "family": "RAW", "home_country": "DE",
     "plants": (
         {"id": "PLT-EUROPOLY-DE", "label": "Ludwigshafen", "origin": "DE", "coef": "1.000000", "lead": 14, "co2": "0.041000", "default": True},
         {"id": "PLT-EUROPOLY-TR", "label": "Izmir", "origin": "TR", "coef": "0.884000", "lead": 33, "co2": "0.139000", "default": False},
     )},
    {"id": "SUP-BALTIC-RAW", "name": "Baltic Raw Materials", "family": "RAW", "home_country": "PL",
     "plants": (
         {"id": "PLT-BALTIC-PL", "label": "Gdansk", "origin": "PL", "coef": "0.962000", "lead": 21, "co2": "0.057000", "default": True},
     )},
    # -- visserie
    {"id": "SUP-BULLONI", "name": "Bulloni SpA", "family": "FIX", "home_country": "IT",
     "plants": (
         {"id": "PLT-BULLONI-IT", "label": "Lecco", "origin": "IT", "coef": "1.000000", "lead": 12, "co2": "0.021000", "default": True},
         {"id": "PLT-BULLONI-TR", "label": "Bursa", "origin": "TR", "coef": "0.920000", "lead": 34, "co2": "0.142000", "default": False},
     )},
    {"id": "SUP-FIXPRO", "name": "FixPro Verbindungstechnik", "family": "FIX", "home_country": "DE",
     "plants": (
         {"id": "PLT-FIXPRO-DE", "label": "Hagen", "origin": "DE", "coef": "1.000000", "lead": 15, "co2": "0.046000", "default": True},
         {"id": "PLT-FIXPRO-CZ", "label": "Plzen", "origin": "CZ", "coef": "0.941000", "lead": 20, "co2": "0.061000", "default": False},
     )},
    {"id": "SUP-ANADOLU-FIX", "name": "Anadolu Fasteners", "family": "FIX", "home_country": "TR",
     "plants": (
         {"id": "PLT-ANADOLU-TR", "label": "Konya", "origin": "TR", "coef": "0.868000", "lead": 38, "co2": "0.151000", "default": True},
     )},
    # -- mécanique
    {"id": "SUP-MECCANICA", "name": "Meccanica Torinese", "family": "MECH", "home_country": "IT",
     "plants": (
         {"id": "PLT-MECCANICA-IT", "label": "Turin", "origin": "IT", "coef": "1.000000", "lead": 8, "co2": "0.009000", "default": True},
         {"id": "PLT-MECCANICA-RO", "label": "Pitesti", "origin": "RO", "coef": "0.913000", "lead": 26, "co2": "0.078000", "default": False},
     )},
    {"id": "SUP-RHEIN-MECH", "name": "Rhein Mechanik", "family": "MECH", "home_country": "DE",
     "plants": (
         {"id": "PLT-RHEIN-DE", "label": "Solingen", "origin": "DE", "coef": "1.000000", "lead": 16, "co2": "0.048000", "default": True},
         {"id": "PLT-RHEIN-CZ", "label": "Brno", "origin": "CZ", "coef": "0.934000", "lead": 22, "co2": "0.063000", "default": False},
     )},
    {"id": "SUP-CARPATI", "name": "Carpati Auto Parts", "family": "MECH", "home_country": "RO",
     "plants": (
         {"id": "PLT-CARPATI-RO", "label": "Brasov", "origin": "RO", "coef": "0.897000", "lead": 28, "co2": "0.081000", "default": True},
     )},
    # -- électricité et électronique
    {"id": "SUP-ELETTRO", "name": "Elettro Lombardia", "family": "ELEC", "home_country": "IT",
     "plants": (
         {"id": "PLT-ELETTRO-IT", "label": "Monza", "origin": "IT", "coef": "1.000000", "lead": 11, "co2": "0.016000", "default": True},
     )},
    {"id": "SUP-BAVARIA-ELEC", "name": "Bavaria Elektronik", "family": "ELEC", "home_country": "DE",
     "plants": (
         {"id": "PLT-BAVARIA-DE", "label": "Regensburg", "origin": "DE", "coef": "1.000000", "lead": 17, "co2": "0.049000", "default": True},
         {"id": "PLT-BAVARIA-HU", "label": "Gyor", "origin": "HU", "coef": "0.926000", "lead": 23, "co2": "0.067000", "default": False},
     )},
    {"id": "SUP-SHENZHEN-EL", "name": "Shenzhen Electronics", "family": "ELEC", "home_country": "CN",
     "plants": (
         {"id": "PLT-SHENZHEN-CN", "label": "Shenzhen", "origin": "CN", "coef": "0.792000", "lead": 62, "co2": "0.348000", "default": True},
     )},
    # -- carrosserie, plastiques, vitrage
    {"id": "SUP-LAMIERA", "name": "Lamiera Veneta", "family": "BODY", "home_country": "IT",
     "plants": (
         {"id": "PLT-LAMIERA-IT", "label": "Vicenza", "origin": "IT", "coef": "1.000000", "lead": 10, "co2": "0.014000", "default": True},
         {"id": "PLT-LAMIERA-SK", "label": "Trnava", "origin": "SK", "coef": "0.938000", "lead": 24, "co2": "0.069000", "default": False},
     )},
    {"id": "SUP-IBERPLAST", "name": "Iberplast", "family": "BODY", "home_country": "ES",
     "plants": (
         {"id": "PLT-IBERPLAST-ES", "label": "Valence", "origin": "ES", "coef": "0.971000", "lead": 18, "co2": "0.053000", "default": True},
     )},
    {"id": "SUP-VETRO", "name": "Vetro Sicuro", "family": "BODY", "home_country": "IT",
     "plants": (
         {"id": "PLT-VETRO-IT", "label": "Pordenone", "origin": "IT", "coef": "1.000000", "lead": 13, "co2": "0.022000", "default": True},
         {"id": "PLT-VETRO-TR", "label": "Istanbul", "origin": "TR", "coef": "0.906000", "lead": 36, "co2": "0.147000", "default": False},
     )},
    # -- garnissage et textile
    {"id": "SUP-TESSUTI", "name": "Tessuti Auto", "family": "TRIM", "home_country": "IT",
     "plants": (
         {"id": "PLT-TESSUTI-IT", "label": "Prato", "origin": "IT", "coef": "1.000000", "lead": 12, "co2": "0.019000", "default": True},
     )},
    {"id": "SUP-MAGHREB-TRIM", "name": "Maghreb Trim", "family": "TRIM", "home_country": "MA",
     "plants": (
         {"id": "PLT-MAGHREB-MA", "label": "Tanger", "origin": "MA", "coef": "0.841000", "lead": 41, "co2": "0.158000", "default": True},
     )},
    {"id": "SUP-VISEGRAD-TRIM", "name": "Visegrad Interiors", "family": "TRIM", "home_country": "CZ",
     "plants": (
         {"id": "PLT-VISEGRAD-CZ", "label": "Ostrava", "origin": "CZ", "coef": "0.929000", "lead": 25, "co2": "0.064000", "default": True},
         {"id": "PLT-VISEGRAD-UA", "label": "Lviv", "origin": "UA", "coef": "0.874000", "lead": 39, "co2": "0.096000", "default": False},
     )},
    # -- fluides
    {"id": "SUP-CHIMICA", "name": "Chimica Adriatica", "family": "FLUID", "home_country": "IT",
     "plants": (
         {"id": "PLT-CHIMICA-IT", "label": "Ravenne", "origin": "IT", "coef": "1.000000", "lead": 7, "co2": "0.024000", "default": True},
     )},
    {"id": "SUP-NORDOIL", "name": "Nordoil", "family": "FLUID", "home_country": "FI",
     "plants": (
         {"id": "PLT-NORDOIL-FI", "label": "Porvoo", "origin": "FI", "coef": "0.954000", "lead": 27, "co2": "0.088000", "default": True},
     )},
)

FAMILY_BY_CATEGORY = {
    "material": "RAW",
    "fastener": "FIX",
    "engine": "MECH",
    "transmission": "MECH",
    "chassis": "MECH",
    "body": "BODY",
    "glazing": "BODY",
    "interior": "TRIM",
    "electrical": "ELEC",
    "fluid": "FLUID",
}


def _digest(*parts: str) -> int:
    return int.from_bytes(
        hashlib.sha256("|".join(parts).encode("utf-8")).digest()[:8], "big"
    )


def _spread(ref: str, salt: str, low: str, high: str, places: str = "0.000001") -> Decimal:
    """Valeur déterministe dans [low, high], stable d'une exécution à l'autre."""
    lo, hi = dec(low), dec(high)
    steps = 10_000
    position = Decimal(_digest(ref, salt) % steps) / Decimal(steps)
    return (lo + (hi - lo) * position).quantize(Decimal(places))


def suppliers_by_family() -> dict[str, list[dict]]:
    families: dict[str, list[dict]] = {}
    for supplier in SUPPLIERS:
        families.setdefault(supplier["family"], []).append(supplier)
    return families


def default_plant(supplier: dict) -> dict:
    for plant in supplier["plants"]:
        if plant["default"]:
            return plant
    return supplier["plants"][0]


def build_sourcing(bom: Bom) -> dict[str, list[dict]]:
    """2 à 3 fournisseurs par pièce achetée, avec leur multiplicateur de prix."""
    families = suppliers_by_family()
    sourcing: dict[str, list[dict]] = {}

    for ref, part in bom.parts.items():
        if part.valuation_mode != PURCHASED:
            continue
        pool = families[FAMILY_BY_CATEGORY[part.category]]
        wanted = min(len(pool), 2 + _digest(ref, "count") % 2)
        start = _digest(ref, "start") % len(pool)
        chosen = [pool[(start + i) % len(pool)] for i in range(wanted)]

        offers = []
        for supplier in chosen:
            offers.append(
                {
                    "supplier_id": supplier["id"],
                    "price_multiplier": _spread(
                        ref, "mult-" + supplier["id"], "0.940000", "1.140000"
                    ),
                }
            )
        # Le fournisseur retenu par défaut est le moins cher à son site par
        # défaut. Choix explicite, pas un effet de bord de l'ordre du fichier.
        cheapest = min(
            offers,
            key=lambda offer: (
                offer["price_multiplier"]
                * dec(default_plant(_supplier_by_id(offer["supplier_id"]))["coef"]),
                offer["supplier_id"],
            ),
        )
        for offer in offers:
            offer["is_default"] = offer is cheapest
        sourcing[ref] = offers

    return sourcing


def _supplier_by_id(supplier_id: str, suppliers: tuple[dict, ...] = SUPPLIERS) -> dict:
    for supplier in suppliers:
        if supplier["id"] == supplier_id:
            return supplier
    raise KeyError(supplier_id)


# Matières premières : le profil de prix se lit sur la référence, plus fiable
# que le libellé (« Fil de cuivre émaillé » n'est pas un câble, mais il suit
# le cuivre comme un câble).
_MATERIAL_PROFILES = (
    ("COPPER", "cable"), ("BRASS", "cable"),
    ("ALU", "aluminium"),
    ("STEEL", "steel"), ("IRON", "steel"), ("STAINLESS", "steel"),
    ("WELD", "steel"), ("ZINC", "steel"), ("LEAD", "steel"),
    ("RUBBER", "rubber"),
    ("PCB", "electronics"), ("SOLDER", "electronics"),
)


def multipla_profile(ref: str, part) -> str:
    """À quels marchés le prix de cette pièce du Multipla est exposé."""
    from .price_drivers import classify

    if part.category == "fastener":
        return "steel"
    if part.category == "material":
        return next((p for token, p in _MATERIAL_PROFILES if token in ref), "default")
    profile = classify(part.label)
    if profile == "default" and part.category == "electrical":
        return "electronics"
    return profile


def build_price_catalog(bom: Bom, indices: dict | None = None) -> dict[str, dict]:
    """Prix de référence et bornes annuelles, dans les trois devises.

    Les prix USD et RUB ne sont pas la conversion exacte du prix EUR : un écart
    déterministe de quelques pourcents est introduit, parce que le modèle les
    traite comme trois prix indépendants et non comme une conversion.

    Chaque pièce porte son profil d'exposition aux indices de marché simulés
    (`drivers`). Avec l'historique des indices, les bornes annuelles sont
    celles que l'API simulée parcourra réellement ; sans lui, elles restent un
    écart déterministe autour de la référence.
    """
    from .price_drivers import daily_factors, weights

    catalog: dict[str, dict] = {}
    for ref, part in bom.parts.items():
        if part.valuation_mode != PURCHASED:
            continue
        eur = part.base_price_eur
        assert eur is not None
        currencies = {
            "EUR": eur,
            "USD": (eur * EUR_TO_USD * _spread(ref, "usd", "0.970000", "1.030000")),
            "RUB": (eur * EUR_TO_RUB * _spread(ref, "rub", "0.950000", "1.050000")),
        }
        profile = multipla_profile(ref, part)
        drivers = weights(profile)
        factors = daily_factors(drivers, indices) if indices else None
        entry = {
            "unit": part.unit,
            "price_per": str(part.price_per),
            "profile": profile,
            "drivers": drivers,
            "prices": {},
        }
        for code, value in currencies.items():
            reference = value.quantize(Decimal("0.000001"))
            if factors:
                series = [reference * f for f in factors]
                bounds = (min(series), max(series))
            else:
                bounds = (
                    reference * _spread(ref, "low-" + code, "0.780000", "0.960000"),
                    reference * _spread(ref, "high-" + code, "1.040000", "1.260000"),
                )
            entry["prices"][code] = {
                "reference": str(reference),
                "year_min": str(bounds[0].quantize(Decimal("0.000001"))),
                "year_max": str(bounds[1].quantize(Decimal("0.000001"))),
            }
        catalog[ref] = entry
    return catalog


def unit_purchase_price(part, offer: dict, plant: dict) -> Decimal:
    """Prix unitaire d'une pièce achetée : les trois facteurs de l'ADR-0010."""
    assert part.base_price_eur is not None
    return (
        part.base_price_eur / part.price_per
        * offer["price_multiplier"]
        * dec(plant["coef"])
    )


def reference_costing(
    bom: Bom,
    cumulative: dict[str, Decimal],
    sourcing: dict[str, list[dict]],
    suppliers: tuple[dict, ...] = SUPPLIERS,
    labour_rate: Decimal = REFERENCE_LABOUR_RATE,
) -> dict:
    """Le coût du scénario vide : fournisseur et usine par défaut, règle `labour`.

    C'est exactement ce que le moteur devra retrouver sur un scénario sans aucun
    paramètre. Ce n'est pas « le prix de la voiture » : c'est une valeur de
    contrôle.

    Deux grandeurs sont produites, et les confondre est l'erreur qui double ou
    perd un coût :

      - le **coût propre** d'une pièce — son prix d'achat, ou sa seule
        main-d'œuvre si elle est fabriquée. Multiplié par la quantité cumulée
        et sommé sur toutes les pièces, il donne le total. C'est la contribution
        de la vue agrégée.
      - le **coût unitaire complet** — pour un ensemble, ses enfants plus sa
        main-d'œuvre. C'est ce qu'on affiche sur une ligne de l'arbre. Il ne se
        somme pas entre niveaux : un parent contient déjà ses enfants.

    Le coût unitaire complet de la racine doit être égal au total des coûts
    propres. C'est l'invariant I1, vérifié ici sur les données réelles.
    """
    material_cost = Decimal(0)
    labour_cost = Decimal(0)
    process_co2 = Decimal(0)
    transport_co2 = Decimal(0)
    per_part: dict[str, dict] = {}

    for ref, part in bom.parts.items():
        quantity = cumulative[ref]
        own_co2 = quantity * part.carbon_factor

        if part.valuation_mode == PURCHASED:
            offer = next(o for o in sourcing[ref] if o["is_default"])
            supplier = _supplier_by_id(offer["supplier_id"], suppliers)
            plant = default_plant(supplier)
            unit_cost = unit_purchase_price(part, offer, plant)
            contribution = quantity * unit_cost
            material_cost += contribution
            assert part.mass_kg is not None
            part_transport = quantity * part.mass_kg * dec(plant["co2"])
            transport_co2 += part_transport
            per_part[ref] = {
                "own_unit_cost": unit_cost,
                "own_contribution": contribution,
                "supplier_id": supplier["id"],
                "plant_id": plant["id"],
                "own_unit_co2": part.carbon_factor + part.mass_kg * dec(plant["co2"]),
                "own_co2_contribution": own_co2 + part_transport,
            }
        else:
            assert part.labour_minutes is not None
            unit_cost = part.labour_minutes / Decimal(60) * labour_rate
            contribution = quantity * unit_cost
            labour_cost += contribution
            per_part[ref] = {
                "own_unit_cost": unit_cost,
                "own_contribution": contribution,
                "supplier_id": None,
                "plant_id": None,
                "own_unit_co2": part.carbon_factor,
                "own_co2_contribution": own_co2,
            }
        process_co2 += own_co2

    full_cost = _roll_up(bom, {r: v["own_unit_cost"] for r, v in per_part.items()})
    full_co2 = _roll_up(bom, {r: v["own_unit_co2"] for r, v in per_part.items()})
    for ref, values in per_part.items():
        values["full_unit_cost"] = full_cost[ref]
        values["full_unit_co2"] = full_co2[ref]

    return {
        "material_cost": material_cost,
        "labour_cost": labour_cost,
        "total_cost": material_cost + labour_cost,
        "own_co2": process_co2,
        "transport_co2": transport_co2,
        "total_co2": process_co2 + transport_co2,
        "root_full_cost": full_cost[bom.root_ref],
        "root_full_co2": full_co2[bom.root_ref],
        "per_part": per_part,
        "labour_rate": labour_rate,
    }


def _roll_up(bom: Bom, own_unit_value: dict[str, Decimal]) -> dict[str, Decimal]:
    """Coût (ou CO2) unitaire complet : le propre, plus celui des enfants."""
    from .graph import children_index, topological_order

    children = children_index(bom)
    rolled: dict[str, Decimal] = {}
    for ref in reversed(topological_order(bom)):
        total = own_unit_value[ref]
        for child_ref, quantity in children[ref]:
            total += quantity * rolled[child_ref]
        rolled[ref] = total
    return rolled
