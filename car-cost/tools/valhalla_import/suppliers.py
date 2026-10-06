"""Fournisseurs et usines de la Valhalla.

Les six fournisseurs nommés par les fichiers source sont repris tels quels, avec
une seule usine, à leur siège : on n'invente pas d'implantation à une entreprise
réelle. Les fournisseurs **alternatifs** sont fictifs — comme ceux du Multipla —
et servent à ce que la page Fournisseurs et la recommandation de sourcing aient
matière à comparer.

Le site d'assemblage est Gaydon (GB) : le CO2 de transport (kg CO2e par kg
transporté) croît avec la distance à Gaydon, le délai aussi. Valeurs
SYNTHÉTIQUES, ordres de grandeur seulement.
"""

from __future__ import annotations

from tools.bom_generator.pricing import _digest, _spread

ASSEMBLY_SITE = "GB"

# -- les fournisseurs des fichiers source ------------------------------------

SOURCE_SUPPLIERS: dict[str, dict] = {
    "Aston Martin / Tier-1 non publié": {
        "id": "SUP-AML-TIER1", "name": "Aston Martin / Tier-1 non publié",
        "family": "OEM", "home_country": "GB", "currency": "GBP",
        "plants": (
            {"id": "PLT-AML-GAYDON", "label": "Gaydon", "origin": "GB", "coef": "1.000000", "lead": 6, "co2": "0.004000", "default": True},
        )},
    "Aston Martin Performance Technologies (AMPT) / Aston Martin": {
        "id": "SUP-AMPT", "name": "Aston Martin Performance Technologies (AMPT)",
        "family": "OEM", "home_country": "GB", "currency": "GBP",
        "plants": (
            {"id": "PLT-AMPT-GAYDON", "label": "Gaydon (AMPT)", "origin": "GB", "coef": "1.000000", "lead": 10, "co2": "0.004000", "default": True},
        )},
    "Würth Industrie Service (candidat de sourcing)": {
        "id": "SUP-WURTH-IS", "name": "Würth Industrie Service",
        "family": "FIX", "home_country": "DE", "currency": "EUR",
        "plants": (
            {"id": "PLT-WURTH-DE", "label": "Bad Mergentheim", "origin": "DE", "coef": "1.000000", "lead": 12, "co2": "0.047000", "default": True},
        )},
    "Bilstein": {
        "id": "SUP-BILSTEIN", "name": "Bilstein",
        "family": "MECH", "home_country": "DE", "currency": "EUR",
        "plants": (
            {"id": "PLT-BILSTEIN-DE", "label": "Ennepetal", "origin": "DE", "coef": "1.000000", "lead": 14, "co2": "0.046000", "default": True},
        )},
    "Brembo": {
        "id": "SUP-BREMBO", "name": "Brembo",
        "family": "MECH", "home_country": "IT", "currency": "EUR",
        "plants": (
            {"id": "PLT-BREMBO-IT", "label": "Curno", "origin": "IT", "coef": "1.000000", "lead": 16, "co2": "0.071000", "default": True},
        )},
    "Michelin": {
        "id": "SUP-MICHELIN", "name": "Michelin",
        "family": "RUBBER", "home_country": "FR", "currency": "EUR",
        "plants": (
            {"id": "PLT-MICHELIN-FR", "label": "Clermont-Ferrand", "origin": "FR", "coef": "1.000000", "lead": 12, "co2": "0.052000", "default": True},
        )},
}

# -- les fournisseurs alternatifs, fictifs -----------------------------------

ALTERNATIVES: tuple[dict, ...] = (
    {"id": "SUP-MIDLANDS-COMP", "name": "Midlands Composites", "family": "COMPOSITE", "home_country": "GB", "currency": "GBP",
     "plants": (
         {"id": "PLT-MIDLANDS-GB", "label": "Coventry", "origin": "GB", "coef": "1.000000", "lead": 9, "co2": "0.005000", "default": True},
         {"id": "PLT-MIDLANDS-CZ", "label": "Brno", "origin": "CZ", "coef": "0.912000", "lead": 21, "co2": "0.083000", "default": False},
     )},
    {"id": "SUP-CARBONIA", "name": "Carbonia Tecnica", "family": "COMPOSITE", "home_country": "IT", "currency": "EUR",
     "plants": (
         {"id": "PLT-CARBONIA-IT", "label": "Modène", "origin": "IT", "coef": "1.000000", "lead": 15, "co2": "0.069000", "default": True},
     )},
    {"id": "SUP-THAMES-ELEC", "name": "Thames Valley Electronics", "family": "ELEC", "home_country": "GB", "currency": "GBP",
     "plants": (
         {"id": "PLT-THAMES-GB", "label": "Reading", "origin": "GB", "coef": "1.000000", "lead": 10, "co2": "0.006000", "default": True},
         {"id": "PLT-THAMES-MY", "label": "Penang", "origin": "MY", "coef": "0.818000", "lead": 58, "co2": "0.312000", "default": False},
     )},
    {"id": "SUP-OBERLAND-ELEK", "name": "Oberland Elektronik", "family": "ELEC", "home_country": "DE", "currency": "EUR",
     "plants": (
         {"id": "PLT-OBERLAND-DE", "label": "Rosenheim", "origin": "DE", "coef": "1.000000", "lead": 14, "co2": "0.051000", "default": True},
         {"id": "PLT-OBERLAND-HU", "label": "Győr", "origin": "HU", "coef": "0.927000", "lead": 20, "co2": "0.076000", "default": False},
     )},
    {"id": "SUP-CELLFORGE", "name": "Cellforge Energy", "family": "HV", "home_country": "GB", "currency": "GBP",
     "plants": (
         {"id": "PLT-CELLFORGE-GB", "label": "Sunderland", "origin": "GB", "coef": "1.000000", "lead": 18, "co2": "0.011000", "default": True},
     )},
    {"id": "SUP-VOLTARIS", "name": "Voltaris Antriebe", "family": "HV", "home_country": "DE", "currency": "EUR",
     "plants": (
         {"id": "PLT-VOLTARIS-DE", "label": "Zwickau", "origin": "DE", "coef": "1.000000", "lead": 16, "co2": "0.053000", "default": True},
         {"id": "PLT-VOLTARIS-PL", "label": "Wrocław", "origin": "PL", "coef": "0.938000", "lead": 21, "co2": "0.072000", "default": False},
     )},
    {"id": "SUP-BLACKCOUNTRY", "name": "Black Country Engineering", "family": "MECH", "home_country": "GB", "currency": "GBP",
     "plants": (
         {"id": "PLT-BLACKCOUNTRY-GB", "label": "Wolverhampton", "origin": "GB", "coef": "1.000000", "lead": 8, "co2": "0.005000", "default": True},
         {"id": "PLT-BLACKCOUNTRY-RO", "label": "Brașov", "origin": "RO", "coef": "0.884000", "lead": 27, "co2": "0.094000", "default": False},
     )},
    {"id": "SUP-SAXONIA", "name": "Saxonia Präzisionsteile", "family": "MECH", "home_country": "DE", "currency": "EUR",
     "plants": (
         {"id": "PLT-SAXONIA-DE", "label": "Chemnitz", "origin": "DE", "coef": "1.000000", "lead": 15, "co2": "0.052000", "default": True},
         {"id": "PLT-SAXONIA-CZ", "label": "Plzeň", "origin": "CZ", "coef": "0.941000", "lead": 19, "co2": "0.067000", "default": False},
     )},
    {"id": "SUP-CASTELLO", "name": "Castello Meccanica", "family": "MECH", "home_country": "IT", "currency": "EUR",
     "plants": (
         {"id": "PLT-CASTELLO-IT", "label": "Maranello", "origin": "IT", "coef": "1.000000", "lead": 14, "co2": "0.070000", "default": True},
     )},
    {"id": "SUP-SEVERN-RUBBER", "name": "Severn Rubber Products", "family": "RUBBER", "home_country": "GB", "currency": "GBP",
     "plants": (
         {"id": "PLT-SEVERN-GB", "label": "Gloucester", "origin": "GB", "coef": "1.000000", "lead": 9, "co2": "0.006000", "default": True},
     )},
    {"id": "SUP-PENNINE-FIX", "name": "Pennine Fasteners", "family": "FIX", "home_country": "GB", "currency": "GBP",
     "plants": (
         {"id": "PLT-PENNINE-GB", "label": "Huddersfield", "origin": "GB", "coef": "1.000000", "lead": 7, "co2": "0.006000", "default": True},
         {"id": "PLT-PENNINE-TR", "label": "Bursa", "origin": "TR", "coef": "0.872000", "lead": 34, "co2": "0.158000", "default": False},
     )},
    {"id": "SUP-ESTUARY-LUBE", "name": "Estuary Lubricants", "family": "FLUID", "home_country": "GB", "currency": "GBP",
     "plants": (
         {"id": "PLT-ESTUARY-GB", "label": "Ellesmere Port", "origin": "GB", "coef": "1.000000", "lead": 6, "co2": "0.008000", "default": True},
     )},
)

ALL_SUPPLIERS: tuple[dict, ...] = tuple(SOURCE_SUPPLIERS.values()) + ALTERNATIVES

#: Quels alternatifs peuvent fournir une pièce, selon son profil de prix.
POOL_BY_PROFILE = {
    "composite": ("SUP-MIDLANDS-COMP", "SUP-CARBONIA"),
    "electronics": ("SUP-THAMES-ELEC", "SUP-OBERLAND-ELEK"),
    "cable": ("SUP-THAMES-ELEC", "SUP-OBERLAND-ELEK"),
    "battery": ("SUP-CELLFORGE", "SUP-VOLTARIS"),
    "motor": ("SUP-VOLTARIS", "SUP-CELLFORGE"),
    "steel": ("SUP-BLACKCOUNTRY", "SUP-SAXONIA", "SUP-CASTELLO"),
    "aluminium": ("SUP-BLACKCOUNTRY", "SUP-SAXONIA", "SUP-CASTELLO"),
    "default": ("SUP-BLACKCOUNTRY", "SUP-SAXONIA", "SUP-CASTELLO"),
    "rubber": ("SUP-SEVERN-RUBBER",),
    "fastener": ("SUP-PENNINE-FIX", "SUP-SAXONIA"),
    "fluid": ("SUP-ESTUARY-LUBE",),
}


def offers_for(ref: str, source_name: str, pool_key: str) -> list[dict]:
    """Le fournisseur du fichier source, retenu par défaut, et 1 ou 2 alternatifs.

    Le défaut reste le fournisseur source à multiplicateur 1 : le prix unitaire
    du scénario vide est alors exactement celui du fichier. Un alternatif peut
    être moins cher — c'est ce que la recommandation de sourcing doit trouver.
    """
    source = SOURCE_SUPPLIERS[source_name]
    pool = [s for s in POOL_BY_PROFILE[pool_key] if s != source["id"]]
    wanted = min(len(pool), 1 + _digest(ref, "alt-count") % 2)
    start = _digest(ref, "alt-start") % len(pool)
    chosen = [pool[(start + i) % len(pool)] for i in range(wanted)]
    offers = [{"supplier_id": source["id"], "price_multiplier": _spread(ref, "src", "1", "1"), "is_default": True}]
    for supplier_id in chosen:
        offers.append(
            {
                "supplier_id": supplier_id,
                "price_multiplier": _spread(ref, "mult-" + supplier_id, "0.930000", "1.150000"),
                "is_default": False,
            }
        )
    return offers
