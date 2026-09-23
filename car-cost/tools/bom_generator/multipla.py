"""Assemblage du véhicule complet et valeurs de contrôle.

Les prix, masses et facteurs carbone sont PLAUSIBLES MAIS SYNTHÉTIQUES : ils ne
proviennent d'aucun constructeur. Voir les métadonnées du jeu de données.
"""

from __future__ import annotations

from . import (
    parts_common,
    system_body,
    system_chassis,
    system_electrical,
    system_interior,
    system_powertrain,
    system_transmission,
)
from .model import Bom, BomBuilder

ROOT = "VEH-MULTIPLA-16V"

# Quantités cumulées vérifiables à la main. Le générateur les recalcule par deux
# algorithmes et refuse le jeu de données si l'une d'elles tombe à côté — c'est
# ce qui fait d'elles des valeurs de contrôle et non des constantes décoratives.
CONTROL_VALUES: dict[str, str] = {
    # 3 segments × 4 attelages mobiles
    "ENG-PISTON-RING": "12",
    # 16 soupapes, dont 8 à l'admission
    "ENG-VALVE-INTAKE": "8",
    # 2 roues avant + 2 roues arrière + 1 roue de secours
    "CHS-TIRE-185-65-15": "5",
    # la porte avant est montée deux fois, chacune avec une vitre
    "CAR-GLASS-DOOR-FRONT": "2",
    # 3 places avant + 3 places arrière
    "INT-SEAT-ASSY": "6",
    # 2 portes avant + 2 portes arrière + capot + hayon, 2 charnières chacun
    "CAR-DOOR-HINGE": "12",
    # 3 supports moteur + 1 support de boîte
    "ENG-MOUNT-ASSY": "4",
    # un capteur par roue freinée
    "ELE-SENSOR-ABS": "4",
    # la même carte électronique équipe les quatre calculateurs
    "ELE-PCB": "4",
    # un haut-parleur par porte
    "ELE-SPEAKER-100": "4",
}


def build_multipla() -> Bom:
    b = BomBuilder()

    parts_common.declare(b)
    system_powertrain.declare(b)
    system_transmission.declare(b)
    system_chassis.declare(b)
    system_body.declare(b)
    system_interior.declare(b)
    system_electrical.declare(b)

    b.assembly(
        ROOT,
        "Fiat Multipla 1.6 16V — véhicule complet",
        system="VEH",
        category="vehicle",
        labour=240,
        children={
            "GMP-ASSY": 1,
            "TRN-ASSY": 1,
            "CHS-ASSY": 1,
            "CAR-ASSY": 1,
            "INT-ASSY": 1,
            "ELE-ASSY": 1,
            "FLU-ASSY": 1,
        },
    )

    return b.build(ROOT)
