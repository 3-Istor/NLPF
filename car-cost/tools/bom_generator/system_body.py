"""Carrosserie (CAR) : caisse en blanc, peinture, ouvrants, vitrage, extérieur."""

from __future__ import annotations

from .model import BomBuilder


def declare(b: BomBuilder) -> None:
    p = lambda ref, label, price, carbon, mass, cat="body": b.purchased(  # noqa: E731
        ref, label, system="CAR", category=cat,
        unit="pce", price=price, carbon=carbon, mass=mass,
    )
    a = lambda ref, label, labour, children, material=None: b.assembly(  # noqa: E731
        ref, label, system="CAR", category="body",
        labour=labour, children=children, material=material,
    )

    # -- caisse en blanc ---------------------------------------------------
    a("CAR-PANEL-FLOOR", "Plancher", 26, {"MAT-STEEL-SHEET": "32.000000"},
      material="MAT-STEEL-SHEET")
    a("CAR-PANEL-SIDE", "Côté de caisse", 22, {"MAT-STEEL-SHEET": "18.500000"},
      material="MAT-STEEL-SHEET")
    a("CAR-PANEL-ROOF", "Pavillon", 16, {"MAT-STEEL-SHEET": "12.400000"},
      material="MAT-STEEL-SHEET")
    a("CAR-RAIL-FRONT", "Longeron avant", 14, {"MAT-STEEL-SHEET": "6.800000"},
      material="MAT-STEEL-SHEET")
    a("CAR-RAIL-REAR", "Longeron arrière", 12, {"MAT-STEEL-SHEET": "5.400000"},
      material="MAT-STEEL-SHEET")
    a("CAR-PILLAR-A", "Pied avant", 11, {"MAT-STEEL-SHEET": "4.200000"},
      material="MAT-STEEL-SHEET")
    a("CAR-PILLAR-B", "Pied milieu", 12, {"MAT-STEEL-SHEET": "5.100000"},
      material="MAT-STEEL-SHEET")
    a("CAR-PILLAR-C", "Pied arrière", 11, {"MAT-STEEL-SHEET": "4.600000"},
      material="MAT-STEEL-SHEET")
    a("CAR-WHEEL-ARCH", "Passage de roue", 8, {"MAT-STEEL-SHEET": "2.300000"},
      material="MAT-STEEL-SHEET")
    a("CAR-BULKHEAD", "Tablier", 18, {"MAT-STEEL-SHEET": "9.200000"},
      material="MAT-STEEL-SHEET")
    a("CAR-COWL", "Auvent", 10, {"MAT-STEEL-SHEET": "3.600000"},
      material="MAT-STEEL-SHEET")

    a("CAR-BIW-ASSY", "Caisse en blanc", 180, {
        "CAR-PANEL-FLOOR": 1, "CAR-PANEL-SIDE": 2, "CAR-PANEL-ROOF": 1,
        "CAR-RAIL-FRONT": 2, "CAR-RAIL-REAR": 2, "CAR-PILLAR-A": 2, "CAR-PILLAR-B": 2,
        "CAR-PILLAR-C": 2, "CAR-WHEEL-ARCH": 4, "CAR-BULKHEAD": 1, "CAR-COWL": 1,
        "MAT-WELD-WIRE": "2.400000", "FIX-WELD-NUT-M8": 40,
    })
    a("CAR-PAINT-SET", "Peinture et protection", 95, {
        "MAT-PAINT-PRIMER": "4.200000", "MAT-PAINT-BASE": "3.800000",
        "MAT-PAINT-CLEAR": "3.100000", "MAT-ZINC-COATING": "2.600000",
        "MAT-ADHESIVE-PU": "1.400000",
    })
    a("CAR-BODY-PAINTED-ASSY", "Caisse peinte", 40, {
        "CAR-BIW-ASSY": 1, "CAR-PAINT-SET": 1, "MAT-BITUMEN-PAD": "6.500000",
    })

    # -- ouvrants ----------------------------------------------------------
    p("CAR-WINDOW-REGULATOR", "Lève-vitre", "34.000000", "2.680000", "1.420000")
    p("CAR-DOOR-LOCK", "Serrure de porte", "26.400000", "1.940000", "0.620000")
    p("CAR-DOOR-HINGE", "Charnière", "9.800000", "0.740000", "0.380000")
    p("CAR-HANDLE-EXT", "Poignée extérieure", "12.400000", "0.860000", "0.180000")
    p("CAR-HANDLE-INT", "Poignée intérieure", "7.600000", "0.420000", "0.096000")
    p("CAR-MIRROR-EXT", "Rétroviseur extérieur", "38.000000", "2.840000", "0.940000")
    p("CAR-HOOD-LATCH", "Serrure de capot", "14.200000", "0.980000", "0.420000")
    p("CAR-HOOD-INSULATION", "Insonorisant de capot", "16.800000", "1.240000", "1.180000")
    p("CAR-GAS-STRUT", "Vérin de hayon", "18.400000", "1.340000", "0.340000")
    p("CAR-GLASS-DOOR-FRONT", "Vitre de porte avant", "28.000000", "2.180000", "3.240000",
      cat="glazing")
    p("CAR-GLASS-DOOR-REAR", "Vitre de porte arrière", "24.000000", "1.920000", "2.860000",
      cat="glazing")
    p("CAR-GLASS-WINDSHIELD", "Pare-brise feuilleté", "96.000000", "7.840000", "12.400000",
      cat="glazing")

    # Joint extrudé et vitrages trempés : formés, donc fabriqués.
    b.assembly("CAR-DOOR-SEAL", "Joint d'ouvrant", system="CAR", category="body",
               labour=8, children={"MAT-EPDM-RUBBER": "0.860000"},
               material="MAT-EPDM-RUBBER")
    b.assembly("CAR-GLASS-TAILGATE", "Vitre de hayon trempée", system="CAR",
               category="glazing", labour=14,
               children={"MAT-GLASS-FLOAT": "7.200000"}, material="MAT-GLASS-FLOAT")
    b.assembly("CAR-GLASS-QUARTER", "Custode latérale trempée", system="CAR",
               category="glazing", labour=9,
               children={"MAT-GLASS-FLOAT": "3.600000"}, material="MAT-GLASS-FLOAT")
    a("CAR-DOOR-SHELL-FRONT", "Caisson de porte avant", 20,
      {"MAT-STEEL-SHEET": "9.400000"}, material="MAT-STEEL-SHEET")
    a("CAR-DOOR-SHELL-REAR", "Caisson de porte arrière", 18,
      {"MAT-STEEL-SHEET": "8.600000"}, material="MAT-STEEL-SHEET")
    a("CAR-HOOD-SHELL", "Caisson de capot", 16, {"MAT-STEEL-SHEET": "11.200000"},
      material="MAT-STEEL-SHEET")
    a("CAR-TAILGATE-SHELL", "Caisson de hayon", 18, {"MAT-STEEL-SHEET": "10.400000"},
      material="MAT-STEEL-SHEET")

    # La porte avant est montée deux fois : sa vitre vaut donc 2.
    a("CAR-DOOR-FRONT-ASSY", "Porte avant équipée", 34, {
        "CAR-DOOR-SHELL-FRONT": 1, "CAR-GLASS-DOOR-FRONT": 1, "CAR-WINDOW-REGULATOR": 1,
        "CAR-DOOR-LOCK": 1, "CAR-DOOR-HINGE": 2, "CAR-DOOR-SEAL": 1,
        "CAR-HANDLE-EXT": 1, "CAR-HANDLE-INT": 1, "CAR-MIRROR-EXT": 1,
        "INT-DOOR-PANEL-FRONT": 1, "ELE-SPEAKER-100": 1, "ELE-HARNESS-DOOR": 1,
        "FIX-M8-20": 6, "FIX-CLIP-PLASTIC": 12,
    })
    a("CAR-DOOR-REAR-ASSY", "Porte arrière équipée", 30, {
        "CAR-DOOR-SHELL-REAR": 1, "CAR-GLASS-DOOR-REAR": 1, "CAR-WINDOW-REGULATOR": 1,
        "CAR-DOOR-LOCK": 1, "CAR-DOOR-HINGE": 2, "CAR-DOOR-SEAL": 1,
        "CAR-HANDLE-EXT": 1, "CAR-HANDLE-INT": 1, "INT-DOOR-PANEL-REAR": 1,
        "ELE-SPEAKER-100": 1, "ELE-HARNESS-DOOR": 1, "FIX-M8-20": 6,
        "FIX-CLIP-PLASTIC": 10,
    })
    a("CAR-HOOD-ASSY", "Capot équipé", 12, {
        "CAR-HOOD-SHELL": 1, "CAR-DOOR-HINGE": 2, "CAR-HOOD-LATCH": 1,
        "CAR-HOOD-INSULATION": 1, "FIX-M8-20": 6,
    })
    a("CAR-TAILGATE-ASSY", "Hayon équipé", 26, {
        "CAR-TAILGATE-SHELL": 1, "CAR-GLASS-TAILGATE": 1, "CAR-DOOR-HINGE": 2,
        "CAR-GAS-STRUT": 2, "CAR-DOOR-LOCK": 1, "CAR-DOOR-SEAL": 1,
        "ELE-WIPER-REAR-MOTOR": 1, "FIX-M8-20": 6,
    })

    # -- éléments extérieurs ----------------------------------------------
    p("CAR-BUMPER-ABSORBER", "Absorbeur de choc", "14.600000", "1.240000", "0.860000")
    p("CAR-BUMPER-BRACKET", "Support de pare-chocs", "8.400000", "0.640000", "0.420000")
    p("CAR-BADGE", "Monogramme", "4.200000", "0.180000", "0.048000")
    p("CAR-MOULDING-SIDE", "Baguette de protection latérale", "11.800000", "0.720000", "0.480000")
    p("CAR-SPARE-CARRIER", "Support de roue de secours", "16.400000", "1.180000", "1.240000")
    p("CAR-JACK", "Cric", "18.600000", "1.640000", "2.480000")
    p("CAR-WHEEL-WRENCH", "Clé de roue", "7.400000", "0.620000", "0.860000")

    a("CAR-BUMPER-SKIN-FRONT", "Peau de pare-chocs avant", 16,
      {"MAT-PP-GRANULE": "4.600000"}, material="MAT-PP-GRANULE")
    a("CAR-BUMPER-SKIN-REAR", "Peau de pare-chocs arrière", 15,
      {"MAT-PP-GRANULE": "4.200000"}, material="MAT-PP-GRANULE")
    a("CAR-BUMPER-BEAM", "Traverse de pare-chocs", 10, {"MAT-STEEL-SHEET": "4.100000"},
      material="MAT-STEEL-SHEET")
    a("CAR-GRILLE", "Calandre", 6, {"MAT-ABS-GRANULE": "0.800000"},
      material="MAT-ABS-GRANULE")
    a("CAR-ARCH-TRIM", "Enjoliveur de passage de roue", 4,
      {"MAT-PP-GRANULE": "0.600000"}, material="MAT-PP-GRANULE")

    a("CAR-BUMPER-FRONT-ASSY", "Pare-chocs avant équipé", 14, {
        "CAR-BUMPER-SKIN-FRONT": 1, "CAR-BUMPER-ABSORBER": 1, "CAR-BUMPER-BEAM": 1,
        "CAR-BUMPER-BRACKET": 2, "ELE-FOG-LAMP": 2, "FIX-M8-20": 8,
        "FIX-CLIP-PLASTIC": 8,
    })
    a("CAR-BUMPER-REAR-ASSY", "Pare-chocs arrière équipé", 12, {
        "CAR-BUMPER-SKIN-REAR": 1, "CAR-BUMPER-ABSORBER": 1, "CAR-BUMPER-BEAM": 1,
        "CAR-BUMPER-BRACKET": 2, "FIX-M8-20": 8, "FIX-CLIP-PLASTIC": 8,
    })
    a("CAR-GLAZING-ASSY", "Vitrage collé", 22, {
        "CAR-GLASS-WINDSHIELD": 1, "CAR-GLASS-QUARTER": 2, "MAT-ADHESIVE-PU": "0.900000",
    })
    a("CAR-TRIM-EXT-ASSY", "Éléments extérieurs", 16, {
        "CAR-GRILLE": 1, "CAR-BADGE": 2, "CAR-MOULDING-SIDE": 2, "CAR-ARCH-TRIM": 4,
        "FIX-CLIP-PLASTIC": 24, "FIX-RIVET-4": 12, "FIX-NUT-M6": 8,
    })
    # La cinquième roue : même pièce que celles des trains.
    a("CAR-SPARE-WHEEL-WELL", "Logement de roue de secours", 8, {
        "CHS-WHEEL-ASSY": 1, "CAR-SPARE-CARRIER": 1, "CAR-JACK": 1,
        "CAR-WHEEL-WRENCH": 1, "FIX-M10-40": 2,
    })

    a("CAR-ASSY", "Carrosserie", 120, {
        "CAR-BODY-PAINTED-ASSY": 1, "CAR-DOOR-FRONT-ASSY": 2, "CAR-DOOR-REAR-ASSY": 2,
        "CAR-HOOD-ASSY": 1, "CAR-TAILGATE-ASSY": 1, "CAR-BUMPER-FRONT-ASSY": 1,
        "CAR-BUMPER-REAR-ASSY": 1, "CAR-GLAZING-ASSY": 1, "CAR-TRIM-EXT-ASSY": 1,
        "CAR-SPARE-WHEEL-WELL": 1, "FIX-M8-20": 24, "FIX-CLIP-PLASTIC": 30,
    })
