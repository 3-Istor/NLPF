"""Châssis et liaison au sol (CHS) : trains, direction, freinage, roues."""

from __future__ import annotations

from .model import BomBuilder


def declare(b: BomBuilder) -> None:
    p = lambda ref, label, price, carbon, mass, unit="pce": b.purchased(  # noqa: E731
        ref, label, system="CHS", category="chassis",
        unit=unit, price=price, carbon=carbon, mass=mass,
    )
    a = lambda ref, label, labour, children, material=None: b.assembly(  # noqa: E731
        ref, label, system="CHS", category="chassis",
        labour=labour, children=children, material=material,
    )

    # -- train avant -------------------------------------------------------
    p("CHS-SHOCK-FRONT", "Amortisseur avant", "46.000000", "4.180000", "3.240000")
    p("CHS-TOP-MOUNT", "Coupelle supérieure de jambe", "14.800000", "0.920000", "0.420000")
    p("CHS-STRUT-BEARING", "Roulement de butée de jambe", "11.600000", "0.780000", "0.240000")
    p("CHS-BUMP-STOP", "Butée de compression", "6.400000", "0.280000", "0.110000")
    p("CHS-DUST-COVER", "Soufflet d'amortisseur", "4.900000", "0.220000", "0.086000")
    p("CHS-BALL-JOINT", "Rotule de suspension", "17.200000", "1.340000", "0.480000")
    p("CHS-ARM-BUSHING", "Silentbloc de bras", "8.600000", "0.420000", "0.180000")
    p("CHS-ARB-FRONT", "Barre stabilisatrice avant", "28.400000", "2.680000", "3.120000")
    p("CHS-ARB-LINK", "Biellette de barre stabilisatrice", "12.800000", "0.860000", "0.280000")
    p("CHS-ARB-BUSHING", "Palier de barre stabilisatrice", "5.200000", "0.240000", "0.094000")
    p("CHS-HUB-CARRIER", "Porte-fusée", "52.000000", "5.640000", "4.180000")
    p("CHS-WHEEL-BEARING", "Roulement de roue", "24.600000", "2.140000", "0.860000")
    p("CHS-HUB-FLANGE", "Moyeu de roue", "31.000000", "3.180000", "2.240000")

    # Les ressorts sont enroulés à partir de fil à ressort.
    a("CHS-SPRING-FRONT", "Ressort de suspension avant", 14,
      {"MAT-STEEL-SPRING": "2.860000"}, material="MAT-STEEL-SPRING")
    a("CHS-SPRING-REAR", "Ressort de suspension arrière", 12,
      {"MAT-STEEL-SPRING": "2.420000"}, material="MAT-STEEL-SPRING")
    a("CHS-SUBFRAME", "Berceau avant", 34, {
        "MAT-STEEL-SHEET": "14.500000", "MAT-WELD-WIRE": "0.350000",
    }, material="MAT-STEEL-SHEET")
    a("CHS-LOWER-ARM", "Bras inférieur", 12, {"MAT-STEEL-SHEET": "3.100000"},
      material="MAT-STEEL-SHEET")
    a("CHS-STRUT-FRONT-ASSY", "Jambe de force avant", 14, {
        "CHS-SHOCK-FRONT": 1, "CHS-SPRING-FRONT": 1, "CHS-TOP-MOUNT": 1,
        "CHS-STRUT-BEARING": 1, "CHS-BUMP-STOP": 1, "CHS-DUST-COVER": 1,
        "FIX-NUT-M10": 1,
    })
    a("CHS-LOWER-ARM-ASSY", "Bras inférieur équipé", 10, {
        "CHS-LOWER-ARM": 1, "CHS-BALL-JOINT": 1, "CHS-ARM-BUSHING": 2, "FIX-M12-60": 2,
    })
    a("CHS-HUB-ASSY", "Moyeu avant équipé", 9, {
        "CHS-HUB-CARRIER": 1, "CHS-WHEEL-BEARING": 1, "CHS-HUB-FLANGE": 1,
        "FIX-BOLT-WHEEL-M12": 4, "FIX-CIRCLIP-20": 1,
    })

    # -- roue : montée quatre fois sur les trains, une cinquième en secours
    p("CHS-RIM-STEEL", "Jante acier 15 pouces", "34.000000", "18.600000", "8.400000")
    p("CHS-TIRE-185-65-15", "Pneumatique 185/65 R15", "42.000000", "31.200000", "8.900000")
    p("CHS-TIRE-VALVE", "Valve de gonflage", "1.400000", "0.060000", "0.012000")
    p("CHS-BALANCE-WEIGHT", "Masse d'équilibrage", "0.900000", "0.040000", "0.020000")
    p("CHS-HUBCAP", "Enjoliveur", "8.600000", "0.640000", "0.420000")

    a("CHS-WHEEL-ASSY", "Roue complète", 6, {
        "CHS-RIM-STEEL": 1, "CHS-TIRE-185-65-15": 1, "CHS-TIRE-VALVE": 1,
        "CHS-BALANCE-WEIGHT": 2, "CHS-HUBCAP": 1,
    })

    # -- freinage ----------------------------------------------------------
    p("CHS-BRAKE-DISC", "Disque de frein avant", "26.400000", "9.840000", "6.200000")
    p("CHS-BRAKE-PAD-SET", "Jeu de plaquettes avant", "18.600000", "1.420000", "1.240000")
    p("CHS-CALIPER", "Étrier de frein avant", "48.000000", "4.860000", "3.640000")
    p("CHS-BRAKE-HOSE", "Flexible de frein", "8.400000", "0.380000", "0.140000")
    p("CHS-BRAKE-DRUM", "Tambour de frein arrière", "22.800000", "8.240000", "5.400000")
    p("CHS-BRAKE-SHOE-SET", "Jeu de mâchoires arrière", "16.200000", "1.180000", "1.680000")
    p("CHS-WHEEL-CYLINDER", "Cylindre de roue", "12.600000", "0.940000", "0.320000")
    p("CHS-DRUM-SPRING-KIT", "Kit de ressorts de tambour", "6.800000", "0.320000", "0.180000")
    p("CHS-MASTER-CYL", "Maître-cylindre", "38.000000", "2.940000", "1.240000")
    p("CHS-BRAKE-SERVO", "Servofrein", "62.000000", "5.180000", "3.860000")
    p("CHS-ABS-UNIT", "Bloc hydraulique ABS", "168.000000", "12.400000", "2.640000")
    p("CHS-BRAKE-LINE", "Canalisation rigide de frein", "7.200000", "0.340000", "0.220000")
    p("CHS-PARK-CABLE", "Câble de frein à main", "14.400000", "0.820000", "0.480000")
    p("CHS-PARK-LEVER", "Levier de frein à main", "18.200000", "1.140000", "0.860000")

    a("CHS-BRAKE-FRONT-ASSY", "Frein avant complet", 10, {
        "CHS-BRAKE-DISC": 1, "CHS-BRAKE-PAD-SET": 1, "CHS-CALIPER": 1,
        "CHS-BRAKE-HOSE": 1, "ELE-SENSOR-ABS": 1, "FIX-M12-60": 2,
    })
    a("CHS-BRAKE-REAR-ASSY", "Frein arrière complet", 12, {
        "CHS-BRAKE-DRUM": 1, "CHS-BRAKE-SHOE-SET": 1, "CHS-WHEEL-CYLINDER": 1,
        "CHS-DRUM-SPRING-KIT": 1, "CHS-BRAKE-HOSE": 1, "ELE-SENSOR-ABS": 1,
        "FIX-M8-20": 4, "FIX-SPRING-PIN-6": 2,
    })
    a("CHS-PEDAL-BOX", "Pédalier", 12, {"MAT-STEEL-SHEET": "2.600000"},
      material="MAT-STEEL-SHEET")
    a("CHS-BRAKE-HYD-ASSY", "Commande de freinage", 18, {
        "CHS-MASTER-CYL": 1, "CHS-BRAKE-SERVO": 1, "CHS-ABS-UNIT": 1,
        "CHS-BRAKE-LINE": 4, "CHS-PARK-CABLE": 2, "CHS-PARK-LEVER": 1,
        "CHS-PEDAL-BOX": 1, "FIX-M8-20": 8, "FIX-NUT-M8": 6,
    })

    a("CHS-FRONT-AXLE-ASSY", "Train avant", 30, {
        "CHS-SUBFRAME": 1, "CHS-STRUT-FRONT-ASSY": 2, "CHS-LOWER-ARM-ASSY": 2,
        "CHS-HUB-ASSY": 2, "CHS-BRAKE-FRONT-ASSY": 2, "CHS-ARB-FRONT": 1,
        "CHS-ARB-LINK": 2, "CHS-ARB-BUSHING": 4, "CHS-WHEEL-ASSY": 2,
        "FIX-M12-60": 8, "FIX-M10-40": 8, "FIX-WASHER-10": 8,
    })

    # -- train arrière -----------------------------------------------------
    p("CHS-SHOCK-REAR", "Amortisseur arrière", "38.000000", "3.460000", "2.680000")
    p("CHS-REAR-BUSHING", "Silentbloc de traverse arrière", "9.400000", "0.460000", "0.210000")
    p("CHS-REAR-HUB-UNIT", "Moyeu arrière monobloc", "42.000000", "4.240000", "2.860000")

    a("CHS-REAR-BEAM", "Traverse arrière", 26, {
        "MAT-STEEL-SHEET": "11.200000", "MAT-WELD-WIRE": "0.280000",
    }, material="MAT-STEEL-SHEET")
    a("CHS-STRUT-REAR-ASSY", "Jambe de force arrière", 11, {
        "CHS-SHOCK-REAR": 1, "CHS-SPRING-REAR": 1, "CHS-TOP-MOUNT": 1,
        "CHS-BUMP-STOP": 1, "FIX-NUT-M10": 1,
    })
    a("CHS-REAR-HUB-ASSY", "Moyeu arrière équipé", 7, {
        "CHS-REAR-HUB-UNIT": 1, "FIX-BOLT-WHEEL-M12": 4, "FIX-M12-60": 4,
    })
    a("CHS-REAR-AXLE-ASSY", "Train arrière", 24, {
        "CHS-REAR-BEAM": 1, "CHS-STRUT-REAR-ASSY": 2, "CHS-REAR-HUB-ASSY": 2,
        "CHS-BRAKE-REAR-ASSY": 2, "CHS-REAR-BUSHING": 4, "CHS-WHEEL-ASSY": 2,
        "FIX-M12-60": 6,
    })

    # -- direction ---------------------------------------------------------
    p("CHS-RACK-PINION", "Pignon de crémaillère", "24.800000", "2.240000", "0.680000")
    p("CHS-RACK-SEAL", "Joint de crémaillère", "5.600000", "0.240000", "0.042000")
    p("CHS-STEERING-BOOT", "Soufflet de crémaillère", "7.800000", "0.360000", "0.120000")
    p("CHS-TIE-ROD-INNER", "Biellette de direction", "16.400000", "1.280000", "0.420000")
    p("CHS-TIE-ROD-END", "Rotule de direction", "14.200000", "1.120000", "0.340000")
    p("CHS-STEERING-COLUMN", "Colonne de direction", "68.000000", "6.480000", "5.240000")
    p("CHS-UJ", "Cardan de colonne", "18.600000", "1.460000", "0.520000")
    p("CHS-PS-HOSE-HP", "Flexible haute pression de direction", "22.400000", "1.180000", "0.480000")
    p("CHS-PS-HOSE-LP", "Flexible retour de direction", "16.800000", "0.920000", "0.380000")

    a("CHS-RACK-HOUSING", "Corps de crémaillère", 16, {"MAT-ALU-CAST": "3.400000"},
      material="MAT-ALU-CAST")
    a("CHS-RACK-BAR", "Barre de crémaillère", 14, {"MAT-STEEL-BAR": "2.200000"},
      material="MAT-STEEL-BAR")
    a("CHS-STEERING-RACK", "Crémaillère de direction assistée", 28, {
        "CHS-RACK-HOUSING": 1, "CHS-RACK-BAR": 1, "CHS-RACK-PINION": 1,
        "CHS-RACK-SEAL": 2, "CHS-STEERING-BOOT": 2, "FIX-M10-40": 4,
    })
    a("CHS-TIE-ROD-ASSY", "Biellette de direction complète", 5, {
        "CHS-TIE-ROD-INNER": 1, "CHS-TIE-ROD-END": 1, "FIX-NUT-M10": 2,
    })
    a("CHS-STEERING-ASSY", "Direction assistée", 20, {
        "CHS-STEERING-RACK": 1, "CHS-TIE-ROD-ASSY": 2, "CHS-STEERING-COLUMN": 1,
        "CHS-UJ": 2, "CHS-PS-HOSE-HP": 1, "CHS-PS-HOSE-LP": 1, "FIX-M10-40": 6,
    })

    a("CHS-ASSY", "Châssis et liaison au sol", 36, {
        "CHS-FRONT-AXLE-ASSY": 1, "CHS-REAR-AXLE-ASSY": 1, "CHS-STEERING-ASSY": 1,
        "CHS-BRAKE-HYD-ASSY": 1, "FIX-M12-60": 12,
    })
