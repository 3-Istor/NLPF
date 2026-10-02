"""Ce que les fichiers Valhalla ne disent pas : masse, carbone, main-d'œuvre.

Tout ici est SYNTHÉTIQUE et déterministe (empreinte SHA-256 de la référence,
jamais de tirage). Les fourchettes visent des ordres de grandeur d'hypercar ;
elles sont écrites en clair pour être relues et discutées, pas cachées dans un
calcul.

Masse : deux familles de règles.
  - Les pièces **ancrées** (monocoque, bloc moteur, cellules, jantes…) ont une
    masse physique connue en ordre de grandeur ; elle est prise telle quelle.
  - Les autres reçoivent une masse brute selon leur profil, puis un **facteur
    d'échelle commun** ramène la masse du véhicule à la cible de la variante.
    Le facteur est borné : s'il sort de [0,4 ; 2,5], les fourchettes sont
    fausses et la génération échoue au lieu de produire un véhicule absurde.
"""

from __future__ import annotations

import re
from decimal import Decimal

from tools.bom_generator.price_drivers import normalize
from tools.bom_generator.pricing import _spread

SCALE6 = Decimal("0.000001")

# -- masses ancrées, kg par unité ---------------------------------------------
# L'ordre compte : la première règle qui correspond l'emporte.
ANCHORED_MASS: tuple[tuple[str, str, str], ...] = (
    (r"^monocoque", "68", "78"),
    (r"^structure superieure carbone", "34", "42"),
    (r"^bloc cylindres", "52", "60"),
    (r"^vilebrequin", "17", "21"),
    (r"^culasse", "13", "16"),
    (r"^boite dct", "92", "108"),
    (r"^cellules batterie haute energie", "0.98", "1.08"),
    (r"^cellules batterie", "0.30", "0.36"),
    (r"^pack batterie", "16", "24"),
    (r"^boitier batterie hv 800", "62", "74"),
    (r"^boitier batterie", "18", "24"),
    (r"^edu avant ensemble", "36", "44"),
    (r"^moteur electrique", "27", "36"),
    (r"^inverter", "8", "11"),
    (r"^jante", "10", "12"),
    (r"^pneu", "11", "13"),
    (r"^disque", "5", "7"),
    (r"^etrier", "4.5", "6"),
    (r"^coque siege", "9", "11"),
    (r"^porte diedre", "13", "16"),
    (r"^pare brise", "11", "13"),
    (r"^sous cadre", "13", "18"),
    (r"^reservoir essence", "8", "11"),
    (r"^faisceau principal", "14", "18"),
    (r"^batterie 12 v", "6", "9"),
    (r"^turbocompresseur", "9", "12"),
    (r"^catalyseur", "4", "6"),
    (r"^silencieux", "6", "9"),
)

# Petites pièces comptées par dizaines ou centaines : clips, connecteurs,
# raccords. Sans cette règle, 400 agrafes au profil « acier » pèseraient une
# tonne et demie.
SMALL_ITEM = re.compile(
    r"\b(?:clips?|agrafes?|connecteurs?|passe fils|grommets?|colliers?|joints? toriques?|"
    r"raccords?|gicleurs?|attaches?|rivets?|inserts?|bouchons?|etiquettes?|"
    r"catadioptres?|buses?)\b"
)
SMALL_ITEM_MASS = ("0.003", "0.040")
#: Au-delà de cette quantité sur une ligne, c'est une petite pièce.
SMALL_ITEM_QUANTITY = Decimal(20)

# -- masses brutes par profil, kg par unité, avant mise à l'échelle -----------
RAW_MASS_BY_PROFILE: dict[str, tuple[str, str]] = {
    "fastener": ("0.004", "0.030"),
    "electronics": ("0.15", "1.20"),
    "cable": ("0.40", "3.00"),
    "composite": ("0.80", "5.00"),
    "aluminium": ("0.80", "5.00"),
    "steel": ("0.40", "4.00"),
    "rubber": ("0.15", "1.20"),
    "motor": ("2.00", "8.00"),
    "battery": ("0.80", "4.00"),
    "default": ("0.30", "2.50"),
}
SENSOR_MASS = ("0.03", "0.15")

# -- densités des fluides, kg par litre ---------------------------------------
DENSITY = (
    (r"essence", "0.745"),
    (r"huile", "0.870"),
    (r"refrigerant", "1.200"),
)
DEFAULT_DENSITY = "1.050"

# -- intensité carbone, kg CO2e par kg de pièce (extraction → sortie d'usine) --
# Mêmes ordres de grandeur que le Multipla, plus la fibre de carbone et les
# cellules, absentes d'une citadine.
CARBON_PER_KG: dict[str, tuple[str, str]] = {
    "steel": ("2.10", "2.70"),
    "aluminium": ("9.00", "12.00"),
    "composite": ("24.00", "30.00"),
    "cable": ("5.50", "7.50"),
    "electronics": ("28.00", "42.00"),
    "battery": ("17.00", "23.00"),
    "motor": ("10.00", "14.00"),
    "rubber": ("3.00", "4.00"),
    "fastener": ("2.40", "3.20"),
    "fluid": ("0.60", "1.40"),
    "default": ("4.00", "6.00"),
}

# -- main-d'œuvre d'assemblage, minutes par ensemble ---------------------------
# Fabrication quasi artisanale : quelques centaines d'heures par véhicule. Le
# temps d'un ensemble = un socle + un temps par ligne posée.
LABOUR_BASE_MINUTES: dict[str, int] = {
    "configuration_vehicule": 90,
    "structure_carrosserie": 2400,
    "aerodynamique_exterieur": 780,
    "vitrage_eclairage": 360,
    "habitacle_securite": 1200,
    "chassis_suspension": 900,
    "direction": 240,
    "freinage": 300,
    "roues_pneus": 120,
    "electrique_basse_tension": 720,
    "electronique_adas": 480,
    "hvac": 360,
    "hydraulique_actif": 420,
    "auxiliaires": 120,
    "consommables": 90,
    "fixations": 480,
    "motorisation": 600,
    "thermique_essence": 1320,
    "hybride_electrique_hv": 960,
    "carburant_essence": 180,
    "echappement": 300,
    "gestion_thermique": 360,
    "transmission": 540,
}
LABOUR_PER_LINE_MINUTES = 8
FINAL_ASSEMBLY_MINUTES = 4200

#: Bornes du facteur d'échelle des masses non ancrées.
SCALE_BOUNDS = (Decimal("0.4"), Decimal("2.5"))


def _range(ref: str, salt: str, bounds: tuple[str, str]) -> Decimal:
    return _spread(ref, salt, bounds[0], bounds[1])


def mass_rule(
    ref: str, label: str, profile: str, quantity: Decimal
) -> tuple[Decimal, bool]:
    """Masse brute par unité, et si elle est ancrée (exclue de la mise à l'échelle).

    Une fixation n'est jamais ancrée : « Vis — Monocoque -> sous-cadre » nomme
    la monocoque, elle n'en a pas la masse.
    """
    name = normalize(label)
    if profile != "fastener":
        for pattern, low, high in ANCHORED_MASS:
            if re.search(pattern, name):
                return _range(ref, "mass", (low, high)), True
        if SMALL_ITEM.search(name) or quantity >= SMALL_ITEM_QUANTITY:
            return _range(ref, "mass", SMALL_ITEM_MASS), False
    if re.search(r"\bcapteurs?\b", name):
        return _range(ref, "mass", SENSOR_MASS), False
    return _range(ref, "mass", RAW_MASS_BY_PROFILE.get(profile, RAW_MASS_BY_PROFILE["default"])), False


def unit_mass(
    ref: str, label: str, unit: str, profile: str, quantity: Decimal
) -> tuple[Decimal, bool]:
    """La masse d'**une unité** telle que la ligne la compte (pièce, kg, g, L)."""
    if unit == "kg":
        return Decimal(1), True
    if unit == "g":
        return Decimal("0.001"), True
    if unit == "L":
        name = normalize(label)
        density = next((d for p, d in DENSITY if re.search(p, name)), DEFAULT_DENSITY)
        return Decimal(density), True
    if unit == "set" and re.search(r"logiciel", normalize(label)):
        return Decimal(0), True  # un logiciel ne pèse rien et ne se transporte pas
    return mass_rule(ref, label, profile, quantity)


def scale_masses(
    lines: list[dict], target_kg: Decimal
) -> tuple[dict[str, Decimal], Decimal]:
    """Applique le facteur commun aux masses non ancrées. `lines` porte
    `ref`, `quantity`, `mass`, `anchored`. Renvoie les masses et le facteur."""
    anchored = sum((l["quantity"] * l["mass"] for l in lines if l["anchored"]), Decimal(0))
    free = sum((l["quantity"] * l["mass"] for l in lines if not l["anchored"]), Decimal(0))
    factor = ((target_kg - anchored) / free).quantize(Decimal("0.0001"))
    low, high = SCALE_BOUNDS
    if not low <= factor <= high:
        raise ValueError(
            f"facteur d'échelle des masses {factor} hors de [{low}, {high}] : "
            f"ancré {anchored} kg, libre {free} kg, cible {target_kg} kg"
        )
    masses = {
        l["ref"]: (l["mass"] if l["anchored"] else l["mass"] * factor).quantize(SCALE6)
        for l in lines
    }
    return masses, factor


def carbon_factor(ref: str, mass: Decimal, profile: str) -> Decimal:
    """kg CO2e par unité = masse × intensité de la matière."""
    intensity = _range(ref, "carbon", CARBON_PER_KG.get(profile, CARBON_PER_KG["default"]))
    return (mass * intensity).quantize(SCALE6)


def labour_minutes(key: str, line_count: int) -> Decimal:
    return Decimal(LABOUR_BASE_MINUTES[key] + LABOUR_PER_LINE_MINUTES * line_count)
