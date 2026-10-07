"""Densités des matières achetées au kilogramme (ADR-0017 §4).

DONNÉES SYNTHÉTIQUES : valeurs rondes et usuelles, validées par l'utilisateur
le 07/10/2026, qui ne viennent d'aucun constructeur ni d'aucune base de
données publique. Aluminium : 2 700 kg/m³ (les nuances réelles vont d'environ
2 660 à 2 800).

Une matière absente de cette table n'a pas de densité : soit parce qu'elle ne
s'achète pas au kilogramme (m², L, g), soit parce qu'elle n'a pas de valeur
usuelle unique (MAT-ADHESIVE-PU, MAT-BITUMEN-PAD, MAT-FOAM-PU,
MAT-GLASS-FIBER). Son champ reste vide, et le serveur refusera d'en déduire
une masse (`MATERIAL_WITHOUT_DENSITY`).
"""

from __future__ import annotations

from decimal import Decimal

DENSITIES_KG_M3: dict[str, Decimal] = {
    ref: Decimal(value)
    for ref, value in {
        "MAT-STEEL-SHEET": "7850",
        "MAT-STAINLESS-SHEET": "7700",
        "MAT-ALU-SHEET": "2700",
        "MAT-ABS-GRANULE": "1050",
        "MAT-PP-GRANULE": "900",
        "MAT-PC-GRANULE": "1200",
        "MAT-GLASS-FLOAT": "2500",
        "MAT-EPDM-RUBBER": "1200",
        "MAT-ALU-CAST": "2700",
        "MAT-BRASS-BAR": "8500",
        "MAT-CAST-IRON": "7200",
        "MAT-CERAMIC-ALO": "3950",
        "MAT-COPPER-WIRE": "8960",
        "MAT-HDPE-GRANULE": "950",
        "MAT-LEAD-INGOT": "11340",
        "MAT-NBR-RUBBER": "1000",
        "MAT-PA66-GRANULE": "1140",
        "MAT-SOLDER-SAC": "7400",
        "MAT-STEEL-BAR": "7850",
        "MAT-STEEL-SPRING": "7850",
        "MAT-WELD-WIRE": "7850",
        "MAT-ZINC-COATING": "7140",
    }.items()
}
