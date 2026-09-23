"""Transmission (TRN) : embrayage, boîte de vitesses, différentiel, arbres."""

from __future__ import annotations

from .model import BomBuilder


def declare(b: BomBuilder) -> None:
    p = lambda ref, label, price, carbon, mass, unit="pce": b.purchased(  # noqa: E731
        ref, label, system="TRN", category="transmission",
        unit=unit, price=price, carbon=carbon, mass=mass,
    )
    a = lambda ref, label, labour, children, material=None: b.assembly(  # noqa: E731
        ref, label, system="TRN", category="transmission",
        labour=labour, children=children, material=material,
    )

    # -- embrayage ---------------------------------------------------------
    p("TRN-CLUTCH-DISC", "Disque d'embrayage", "34.000000", "2.640000", "1.820000")
    p("TRN-PRESSURE-PLATE", "Mécanisme d'embrayage", "58.000000", "4.180000", "3.240000")
    p("TRN-RELEASE-BEARING", "Butée d'embrayage", "18.500000", "1.240000", "0.320000")
    p("TRN-CLUTCH-FORK", "Fourchette d'embrayage", "11.200000", "0.860000", "0.410000")
    p("TRN-CLUTCH-MASTER-CYL", "Émetteur d'embrayage", "26.400000", "1.480000", "0.380000")
    p("TRN-CLUTCH-SLAVE-CYL", "Récepteur d'embrayage", "22.800000", "1.320000", "0.340000")
    p("TRN-CLUTCH-LINE", "Canalisation d'embrayage", "9.600000", "0.480000", "0.160000")

    a("TRN-CLUTCH-ASSY", "Embrayage complet", 18, {
        "TRN-CLUTCH-DISC": 1, "TRN-PRESSURE-PLATE": 1, "TRN-RELEASE-BEARING": 1,
        "TRN-CLUTCH-FORK": 1, "FIX-M8-20": 6,
    })
    a("TRN-CLUTCH-HYD-ASSY", "Commande hydraulique d'embrayage", 8, {
        "TRN-CLUTCH-MASTER-CYL": 1, "TRN-CLUTCH-SLAVE-CYL": 1, "TRN-CLUTCH-LINE": 1,
        "FIX-M8-20": 4,
    })

    # -- boîte de vitesses -------------------------------------------------
    p("TRN-INPUT-SHAFT", "Arbre primaire", "64.000000", "6.200000", "3.400000")
    p("TRN-OUTPUT-SHAFT", "Arbre secondaire", "72.000000", "6.800000", "3.900000")
    p("TRN-GEAR-SET", "Couple de pignons de vitesse", "28.500000", "2.940000", "1.240000")
    p("TRN-SYNCHRO-RING", "Bague de synchroniseur", "12.400000", "1.080000", "0.180000")
    p("TRN-REVERSE-IDLER", "Pignon de marche arrière", "21.000000", "1.920000", "0.860000")
    p("TRN-BEARING-TAPER", "Roulement conique de boîte", "16.800000", "1.460000", "0.420000")
    p("TRN-BEARING-BALL", "Roulement à billes de boîte", "11.900000", "0.980000", "0.260000")
    p("TRN-SHIFT-FORK", "Fourchette de passage", "14.200000", "1.120000", "0.340000")
    p("TRN-SELECTOR-SHAFT", "Axe de sélection", "18.600000", "1.380000", "0.620000")
    p("TRN-OIL-SEAL", "Joint spi de boîte", "4.800000", "0.180000", "0.038000")

    a("TRN-GEARBOX-HOUSING", "Carter de boîte de vitesses", 32,
      {"MAT-ALU-CAST": "8.600000"}, material="MAT-ALU-CAST")
    a("TRN-GEARSHAFT-ASSY", "Arbres et pignonnerie", 26, {
        "TRN-INPUT-SHAFT": 1, "TRN-OUTPUT-SHAFT": 1, "TRN-GEAR-SET": 5,
        "TRN-SYNCHRO-RING": 5, "TRN-REVERSE-IDLER": 1, "TRN-BEARING-TAPER": 4,
        "FIX-CIRCLIP-20": 8,
    })

    # -- différentiel ------------------------------------------------------
    p("TRN-CROWN-WHEEL", "Couronne de différentiel", "48.000000", "4.620000", "2.840000")
    p("TRN-PINION", "Pignon d'attaque", "36.000000", "3.480000", "1.620000")
    p("TRN-PLANET-GEAR", "Satellite de différentiel", "14.600000", "1.240000", "0.480000")
    p("TRN-SUN-GEAR", "Planétaire de différentiel", "17.800000", "1.560000", "0.620000")
    p("TRN-DIFF-BEARING", "Roulement de différentiel", "19.400000", "1.680000", "0.520000")

    a("TRN-DIFF-ASSY", "Différentiel", 22, {
        "TRN-CROWN-WHEEL": 1, "TRN-PINION": 1, "TRN-PLANET-GEAR": 4, "TRN-SUN-GEAR": 2,
        "TRN-DIFF-BEARING": 2, "FIX-M10-40": 8,
    })
    a("TRN-GEARBOX-ASSY", "Boîte de vitesses assemblée", 48, {
        "TRN-GEARBOX-HOUSING": 1, "TRN-GEARSHAFT-ASSY": 1, "TRN-DIFF-ASSY": 1,
        "TRN-SHIFT-FORK": 3, "TRN-SELECTOR-SHAFT": 1, "TRN-OIL-SEAL": 3,
        "TRN-BEARING-BALL": 2, "FIX-M8-20": 14, "FIX-M10-40": 4, "FIX-WASHER-8": 14,
    })

    # -- arbres de transmission (montés deux fois) ------------------------
    p("TRN-CV-JOINT-OUTER", "Joint homocinétique extérieur", "42.000000", "3.860000", "1.640000")
    p("TRN-CV-JOINT-INNER", "Joint homocinétique intérieur", "38.000000", "3.520000", "1.480000")
    p("TRN-CV-BOOT", "Soufflet de cardan", "8.400000", "0.420000", "0.180000")
    p("TRN-BOOT-CLAMP", "Collier de soufflet", "1.900000", "0.070000", "0.014000")
    p("TRN-CV-GREASE", "Graisse de cardan", "6.200000", "0.340000", "0.220000", "kg")

    a("TRN-SHAFT-BAR", "Barre d'arbre de transmission", 10,
      {"MAT-STEEL-BAR": "3.200000"}, material="MAT-STEEL-BAR")
    a("TRN-DRIVESHAFT-ASSY", "Arbre de transmission complet", 14, {
        "TRN-SHAFT-BAR": 1, "TRN-CV-JOINT-OUTER": 1, "TRN-CV-JOINT-INNER": 1,
        "TRN-CV-BOOT": 2, "TRN-BOOT-CLAMP": 4, "TRN-CV-GREASE": "0.240000",
    })

    # -- commande de vitesses ---------------------------------------------
    p("TRN-SHIFT-LEVER", "Levier de vitesses", "16.400000", "0.940000", "0.480000")
    p("TRN-SHIFT-CABLE", "Câble de commande de boîte", "13.800000", "0.760000", "0.320000")
    p("TRN-SHIFT-KNOB", "Pommeau de levier", "7.600000", "0.380000", "0.140000")
    p("TRN-SHIFT-BUSHING", "Bague de tringlerie", "2.400000", "0.090000", "0.018000")

    a("TRN-SHIFTER-ASSY", "Commande de vitesses", 12, {
        "TRN-SHIFT-LEVER": 1, "TRN-SHIFT-CABLE": 2, "TRN-SHIFT-KNOB": 1,
        "TRN-SHIFT-BUSHING": 4, "FIX-M6-16": 6, "FIX-SPRING-PIN-6": 2,
    })

    # Le support élastique vient du groupe motopropulseur : c'est la même
    # pièce, montée ici une quatrième fois.
    a("TRN-ASSY", "Transmission", 40, {
        "TRN-CLUTCH-ASSY": 1, "TRN-CLUTCH-HYD-ASSY": 1, "TRN-GEARBOX-ASSY": 1,
        "TRN-DRIVESHAFT-ASSY": 2, "TRN-SHIFTER-ASSY": 1, "ENG-MOUNT-ASSY": 1,
        "FIX-M10-40": 10,
    })
