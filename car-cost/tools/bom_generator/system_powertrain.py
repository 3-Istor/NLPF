"""Groupe motopropulseur (GMP) : moteur 1.6 16V et ses sous-ensembles."""

from __future__ import annotations

from .model import BomBuilder


def declare(b: BomBuilder) -> None:
    p = lambda ref, label, price, carbon, mass, unit="pce": b.purchased(  # noqa: E731
        ref, label, system="GMP", category="engine",
        unit=unit, price=price, carbon=carbon, mass=mass,
    )
    a = lambda ref, label, labour, children, material=None: b.assembly(  # noqa: E731
        ref, label, system="GMP", category="engine",
        labour=labour, children=children, material=material,
    )

    # -- bloc-cylindres ----------------------------------------------------
    p("ENG-PISTON-RING", "Segment de piston", "1.850000", "0.190000", "0.012000")
    p("ENG-PISTON-PIN", "Axe de piston", "2.400000", "0.260000", "0.088000")
    p("ENG-ROD-BEARING", "Coussinet de bielle", "1.950000", "0.210000", "0.032000")
    p("ENG-MAIN-BEARING", "Coussinet de palier", "2.300000", "0.240000", "0.041000")
    p("ENG-THRUST-WASHER", "Cale de butée de vilebrequin", "1.600000", "0.150000", "0.018000")
    p("ENG-CRANK-SPROCKET", "Pignon de vilebrequin", "6.800000", "0.720000", "0.310000")
    p("ENG-FLYWHEEL", "Volant moteur", "48.000000", "14.200000", "7.400000")
    p("ENG-SEAL-CRANK-FRONT", "Joint spi avant de vilebrequin", "3.200000", "0.120000", "0.024000")
    p("ENG-SEAL-CRANK-REAR", "Joint spi arrière de vilebrequin", "4.100000", "0.150000", "0.031000")
    p("ENG-OIL-PAN-GASKET", "Joint de carter d'huile", "5.600000", "0.190000", "0.062000")
    p("ENG-DRAIN-PLUG", "Bouchon de vidange", "1.700000", "0.060000", "0.042000")
    p("ENG-DIPSTICK", "Jauge à huile", "2.800000", "0.110000", "0.048000")
    p("ENG-DIPSTICK-TUBE", "Tube de jauge", "3.400000", "0.140000", "0.071000")

    a("ENG-BLOCK-RAW", "Bloc-cylindres usiné", 48, {"MAT-CAST-IRON": "34.000000"},
      material="MAT-CAST-IRON")
    a("ENG-PISTON", "Piston", 9, {"MAT-ALU-CAST": "0.380000"}, material="MAT-ALU-CAST")
    a("ENG-CONROD", "Bielle", 14, {"MAT-STEEL-BAR": "0.720000"}, material="MAT-STEEL-BAR")
    a("ENG-CRANKSHAFT", "Vilebrequin", 38, {"MAT-STEEL-BAR": "12.500000"},
      material="MAT-STEEL-BAR")
    a("ENG-OIL-PAN", "Carter d'huile", 12, {"MAT-STEEL-SHEET": "2.400000"},
      material="MAT-STEEL-SHEET")

    # L'attelage mobile est monté quatre fois : ses segments valent 3 × 4 = 12.
    a("ENG-PISTON-ROD-ASSY", "Attelage mobile complet", 11, {
        "ENG-PISTON": 1, "ENG-PISTON-RING": 3, "ENG-PISTON-PIN": 1, "ENG-CONROD": 1,
        "ENG-ROD-BEARING": 2, "FIX-M8-35": 2, "FIX-CIRCLIP-20": 2,
    })
    a("ENG-CRANK-ASSY", "Vilebrequin équipé", 16, {
        "ENG-CRANKSHAFT": 1, "ENG-MAIN-BEARING": 10, "ENG-THRUST-WASHER": 2,
        "ENG-CRANK-SPROCKET": 1, "FIX-M10-40": 10,
    })
    a("ENG-OIL-PAN-ASSY", "Carter d'huile équipé", 8, {
        "ENG-OIL-PAN": 1, "ENG-OIL-PAN-GASKET": 1, "ENG-DRAIN-PLUG": 1, "FIX-M6-16": 16, "FIX-WASHER-6": 16,
    })
    a("ENG-BLOCK-ASSY", "Bloc-cylindres assemblé", 42, {
        "ENG-BLOCK-RAW": 1, "ENG-PISTON-ROD-ASSY": 4, "ENG-CRANK-ASSY": 1,
        "ENG-OIL-PAN-ASSY": 1, "ENG-FLYWHEEL": 1, "ENG-SEAL-CRANK-FRONT": 1,
        "ENG-SEAL-CRANK-REAR": 1, "ENG-DIPSTICK": 1, "ENG-DIPSTICK-TUBE": 1,
        "FIX-M8-20": 8, "FIX-WASHER-8": 8,
    })

    # -- culasse -----------------------------------------------------------
    p("ENG-VALVE-INTAKE", "Soupape d'admission", "3.100000", "0.340000", "0.062000")
    p("ENG-VALVE-EXHAUST", "Soupape d'échappement", "3.900000", "0.410000", "0.058000")
    p("ENG-VALVE-SPRING", "Ressort de soupape", "1.200000", "0.090000", "0.021000")
    p("ENG-VALVE-GUIDE", "Guide de soupape", "0.950000", "0.070000", "0.014000")
    p("ENG-VALVE-SEAL", "Joint de queue de soupape", "0.650000", "0.030000", "0.003000")
    p("ENG-VALVE-COLLET", "Clavette de soupape", "0.350000", "0.020000", "0.002000")
    p("ENG-VALVE-RETAINER", "Coupelle de ressort", "0.900000", "0.060000", "0.011000")
    p("ENG-HYDRAULIC-LIFTER", "Poussoir hydraulique", "6.200000", "0.540000", "0.046000")
    p("ENG-CAMSHAFT-INTAKE", "Arbre à cames d'admission", "42.000000", "4.800000", "3.200000")
    p("ENG-CAMSHAFT-EXHAUST", "Arbre à cames d'échappement", "42.000000", "4.800000", "3.200000")
    p("ENG-CAM-BEARING", "Chapeau de palier d'arbre à cames", "2.100000", "0.180000", "0.052000")
    p("ENG-CAM-COVER-GASKET", "Joint de cache-culbuteurs", "7.400000", "0.240000", "0.084000")
    p("ENG-HEAD-GASKET", "Joint de culasse", "18.500000", "0.880000", "0.290000")

    a("ENG-HEAD-RAW", "Culasse usinée", 44, {"MAT-ALU-CAST": "11.500000"},
      material="MAT-ALU-CAST")
    a("ENG-CAM-COVER", "Cache-culbuteurs", 9, {"MAT-ALU-SHEET": "1.200000"},
      material="MAT-ALU-SHEET")
    a("ENG-HEAD-ASSY", "Culasse assemblée 16 soupapes", 56, {
        "ENG-HEAD-RAW": 1, "ENG-VALVE-INTAKE": 8, "ENG-VALVE-EXHAUST": 8,
        "ENG-VALVE-SPRING": 16, "ENG-VALVE-GUIDE": 16, "ENG-VALVE-SEAL": 16,
        "ENG-VALVE-COLLET": 32, "ENG-VALVE-RETAINER": 16, "ENG-HYDRAULIC-LIFTER": 16,
        "ENG-CAMSHAFT-INTAKE": 1, "ENG-CAMSHAFT-EXHAUST": 1, "ENG-CAM-BEARING": 10,
        "ENG-CAM-COVER": 1, "ENG-CAM-COVER-GASKET": 1, "ENG-HEAD-GASKET": 1,
        "FIX-M12-60": 10, "FIX-M6-25": 12,
    })

    # -- distribution ------------------------------------------------------
    p("ENG-TIMING-BELT", "Courroie de distribution", "14.800000", "0.920000", "0.240000")
    p("ENG-TIMING-TENSIONER", "Galet tendeur de distribution", "22.400000", "1.640000", "0.310000")
    p("ENG-TIMING-IDLER", "Galet enrouleur", "16.200000", "1.180000", "0.260000")
    p("ENG-CAM-SPROCKET", "Pignon d'arbre à cames", "11.500000", "1.020000", "0.480000")
    p("ENG-CRANK-PULLEY", "Poulie damper de vilebrequin", "26.500000", "2.340000", "1.850000")

    a("ENG-TIMING-COVER", "Carter de distribution", 6, {"MAT-PP-GRANULE": "0.900000"},
      material="MAT-PP-GRANULE")
    a("ENG-TIMING-ASSY", "Distribution complète", 24, {
        "ENG-TIMING-BELT": 1, "ENG-TIMING-TENSIONER": 1, "ENG-TIMING-IDLER": 2,
        "ENG-CAM-SPROCKET": 2, "ENG-CRANK-PULLEY": 1, "ENG-TIMING-COVER": 1,
        "FIX-M8-20": 6, "FIX-M6-16": 8, "FIX-WASHER-6": 8,
    })

    # -- lubrification -----------------------------------------------------
    p("ENG-OIL-PUMP-ROTOR", "Rotor de pompe à huile", "9.400000", "0.860000", "0.340000")
    p("ENG-OIL-RELIEF-VALVE", "Clapet de décharge", "3.700000", "0.220000", "0.045000")
    p("ENG-OIL-PICKUP", "Crépine d'aspiration", "8.600000", "0.480000", "0.210000")
    p("ENG-OIL-FILTER", "Filtre à huile", "4.900000", "0.360000", "0.320000")
    p("ENG-OIL-FILTER-HOUSING", "Support de filtre à huile", "12.300000", "1.140000", "0.520000")
    p("ENG-OIL-PRESSURE-SWITCH", "Manocontact de pression d'huile", "6.300000", "0.290000", "0.038000")

    a("ENG-OIL-PUMP-HOUSING", "Corps de pompe à huile", 10, {"MAT-ALU-CAST": "1.100000"},
      material="MAT-ALU-CAST")
    a("ENG-OIL-PUMP", "Pompe à huile", 14, {
        "ENG-OIL-PUMP-HOUSING": 1, "ENG-OIL-PUMP-ROTOR": 1, "ENG-OIL-RELIEF-VALVE": 1,
        "FIX-M6-16": 4,
    })
    a("ENG-LUB-ASSY", "Circuit de lubrification", 12, {
        "ENG-OIL-PUMP": 1, "ENG-OIL-PICKUP": 1, "ENG-OIL-FILTER": 1,
        "ENG-OIL-FILTER-HOUSING": 1, "ENG-OIL-PRESSURE-SWITCH": 1, "FIX-M6-16": 6,
    })

    # -- refroidissement ---------------------------------------------------
    p("ENG-RAD-SEAL", "Joint de boîte à eau", "2.900000", "0.110000", "0.026000")
    p("ENG-RAD-DRAIN-PLUG", "Bouchon de vidange radiateur", "1.900000", "0.070000", "0.014000")
    p("ENG-FAN-MOTOR", "Moteur de ventilateur", "24.000000", "3.100000", "1.240000")
    p("ENG-FAN-BLADE", "Hélice de ventilateur", "7.600000", "0.940000", "0.380000")
    p("ENG-WATER-PUMP", "Pompe à eau", "28.000000", "2.680000", "1.420000")
    p("ENG-THERMOSTAT", "Thermostat", "7.900000", "0.410000", "0.092000")
    p("ENG-HOSE-COOL-32", "Durite de refroidissement Ø32", "6.400000", "0.380000", "0.180000")
    p("ENG-HOSE-COOL-20", "Durite de chauffage Ø20", "4.200000", "0.240000", "0.110000")
    p("ENG-EXP-TANK-CAP", "Bouchon de vase d'expansion", "3.100000", "0.120000", "0.034000")

    a("ENG-RAD-CORE", "Faisceau de radiateur", 18, {
        "MAT-ALU-SHEET": "2.800000", "MAT-BRASS-BAR": "0.240000",
    }, material="MAT-ALU-SHEET")
    a("ENG-RAD-TANK", "Boîte à eau de radiateur", 5, {"MAT-PA66-GRANULE": "0.450000"},
      material="MAT-PA66-GRANULE")
    a("ENG-RADIATOR", "Radiateur de refroidissement", 16, {
        "ENG-RAD-CORE": 1, "ENG-RAD-TANK": 2, "ENG-RAD-SEAL": 2,
        "ENG-RAD-DRAIN-PLUG": 1, "FIX-CLIP-PLASTIC": 8,
    })
    a("ENG-FAN-SHROUD", "Buse de ventilateur", 7, {"MAT-PP-GRANULE": "1.400000"},
      material="MAT-PP-GRANULE")
    a("ENG-FAN-ASSY", "Groupe motoventilateur", 10, {
        "ENG-FAN-MOTOR": 1, "ENG-FAN-BLADE": 1, "ENG-FAN-SHROUD": 1,
        "ELE-CONNECTOR-2P": 1, "FIX-M6-16": 4,
    })
    a("ENG-THERMOSTAT-HOUSING", "Boîtier de thermostat", 4,
      {"MAT-PA66-GRANULE": "0.220000"}, material="MAT-PA66-GRANULE")
    a("ENG-EXPANSION-TANK", "Vase d'expansion", 6, {"MAT-PP-GRANULE": "0.550000"},
      material="MAT-PP-GRANULE")
    a("ENG-COOL-ASSY", "Circuit de refroidissement", 22, {
        "ENG-RADIATOR": 1, "ENG-FAN-ASSY": 1, "ENG-WATER-PUMP": 1, "ENG-THERMOSTAT": 1,
        "ENG-THERMOSTAT-HOUSING": 1, "ENG-HOSE-COOL-32": 2, "ENG-HOSE-COOL-20": 2,
        "ENG-EXPANSION-TANK": 1, "ENG-EXP-TANK-CAP": 1, "ELE-SENSOR-COOLANT-TEMP": 1,
        "FIX-HOSE-CLAMP-40": 4, "FIX-HOSE-CLAMP-25": 6, "FIX-M6-16": 6,
    })

    # -- alimentation carburant -------------------------------------------
    p("ENG-FUEL-PUMP-MODULE", "Module de pompe à carburant", "78.000000", "6.400000", "1.860000")
    p("ENG-FUEL-LEVEL-SENDER", "Jauge de niveau de carburant", "18.400000", "0.940000", "0.180000")
    p("ENG-FUEL-FILTER", "Filtre à carburant", "11.200000", "0.620000", "0.290000")
    p("ENG-INJECTOR", "Injecteur", "32.000000", "1.840000", "0.086000")
    p("ENG-FUEL-REGULATOR", "Régulateur de pression carburant", "16.500000", "0.780000", "0.120000")
    p("ENG-FUEL-CAP", "Bouchon de réservoir", "6.800000", "0.310000", "0.098000")

    a("ENG-FUEL-TANK", "Réservoir de carburant", 26, {"MAT-HDPE-GRANULE": "8.500000"},
      material="MAT-HDPE-GRANULE")
    a("ENG-TANK-STRAP", "Sangle de réservoir", 6, {"MAT-STEEL-SHEET": "1.100000"},
      material="MAT-STEEL-SHEET")
    a("ENG-FUEL-RAIL", "Rampe d'injection", 9, {"MAT-STEEL-BAR": "0.650000"},
      material="MAT-STEEL-BAR")
    a("ENG-FUEL-LINE", "Canalisation de carburant", 6, {
        "MAT-NBR-RUBBER": "0.220000", "MAT-STEEL-BAR": "0.180000",
    }, material="MAT-NBR-RUBBER")
    a("ENG-FUEL-ASSY", "Circuit d'alimentation carburant", 28, {
        "ENG-FUEL-TANK": 1, "ENG-TANK-STRAP": 2, "ENG-FUEL-PUMP-MODULE": 1,
        "ENG-FUEL-LEVEL-SENDER": 1, "ENG-FUEL-FILTER": 1, "ENG-FUEL-RAIL": 1,
        "ENG-INJECTOR": 4, "ENG-FUEL-REGULATOR": 1, "ENG-FUEL-LINE": 2,
        "ENG-FUEL-CAP": 1, "FIX-HOSE-CLAMP-25": 6, "FIX-M8-20": 6,
    })

    # -- admission ---------------------------------------------------------
    p("ENG-THROTTLE-BODY", "Boîtier papillon", "86.000000", "5.200000", "1.140000")
    p("ENG-AIR-FILTER-ELEMENT", "Élément filtrant à air", "7.300000", "0.420000", "0.310000")
    p("ENG-AIR-DUCT", "Conduit d'admission souple", "12.600000", "0.680000", "0.420000")
    p("ENG-INTAKE-GASKET", "Joint de collecteur d'admission", "6.100000", "0.220000", "0.054000")

    a("ENG-INTAKE-MANIFOLD", "Collecteur d'admission", 16, {
        "MAT-PA66-GRANULE": "2.100000", "MAT-GLASS-FIBER": "0.400000",
    }, material="MAT-PA66-GRANULE")
    a("ENG-AIRBOX-HOUSING", "Corps de boîtier de filtre à air", 8,
      {"MAT-PP-GRANULE": "1.300000"}, material="MAT-PP-GRANULE")
    a("ENG-AIRBOX-LID", "Couvercle de boîtier de filtre à air", 5,
      {"MAT-PP-GRANULE": "0.700000"}, material="MAT-PP-GRANULE")
    a("ENG-AIRBOX-ASSY", "Boîtier de filtre à air complet", 8, {
        "ENG-AIRBOX-HOUSING": 1, "ENG-AIRBOX-LID": 1, "ENG-AIR-FILTER-ELEMENT": 1,
        "ENG-AIR-DUCT": 1, "FIX-CLIP-PLASTIC": 6, "FIX-SCREW-TORX-M5": 4,
    })
    a("ENG-INTAKE-ASSY", "Circuit d'admission", 18, {
        "ENG-INTAKE-MANIFOLD": 1, "ENG-THROTTLE-BODY": 1, "ENG-AIRBOX-ASSY": 1,
        "ELE-SENSOR-MAF": 1, "ELE-SENSOR-MAP": 1, "ENG-INTAKE-GASKET": 1,
        "FIX-M8-20": 8, "FIX-STUD-M8": 4, "FIX-NUT-M8": 4,
    })

    # -- échappement -------------------------------------------------------
    p("ENG-CAT-MAT", "Natte de maintien du catalyseur", "8.900000", "0.460000", "0.180000")
    p("ENG-EXH-HANGER", "Silentbloc d'échappement", "2.400000", "0.140000", "0.048000")
    p("ENG-EXH-GASKET", "Joint d'échappement", "4.200000", "0.190000", "0.042000")
    p("ENG-EXH-CLAMP", "Collier d'échappement", "5.600000", "0.280000", "0.096000")

    a("ENG-EXH-MANIFOLD", "Collecteur d'échappement", 18, {"MAT-CAST-IRON": "5.400000"},
      material="MAT-CAST-IRON")
    a("ENG-CAT-SUBSTRATE", "Support catalytique imprégné", 12, {
        "MAT-CERAMIC-ALO": "1.200000", "MAT-PGM-CATALYST": "3.200000",
    }, material="MAT-CERAMIC-ALO")
    a("ENG-CAT-SHELL", "Enveloppe de catalyseur", 14, {"MAT-STAINLESS-SHEET": "2.600000"},
      material="MAT-STAINLESS-SHEET")
    a("ENG-CATALYST", "Catalyseur", 16, {
        "ENG-CAT-SUBSTRATE": 1, "ENG-CAT-SHELL": 1, "ENG-CAT-MAT": 1,
    })
    a("ENG-EXH-FRONT-PIPE", "Tube avant d'échappement", 12,
      {"MAT-STAINLESS-SHEET": "3.100000"}, material="MAT-STAINLESS-SHEET")
    a("ENG-SILENCER-CENTER", "Silencieux intermédiaire", 16,
      {"MAT-STAINLESS-SHEET": "4.200000"}, material="MAT-STAINLESS-SHEET")
    a("ENG-SILENCER-REAR", "Silencieux arrière", 18,
      {"MAT-STAINLESS-SHEET": "5.600000"}, material="MAT-STAINLESS-SHEET")
    a("ENG-EXHAUST-ASSY", "Ligne d'échappement", 26, {
        "ENG-EXH-MANIFOLD": 1, "ENG-CATALYST": 1, "ENG-EXH-FRONT-PIPE": 1,
        "ENG-SILENCER-CENTER": 1, "ENG-SILENCER-REAR": 1, "ENG-EXH-HANGER": 4,
        "ENG-EXH-GASKET": 3, "ENG-EXH-CLAMP": 3, "ELE-SENSOR-LAMBDA": 2,
        "FIX-NUT-EXHAUST-M8": 8, "FIX-STUD-M8": 6,
    })

    # -- allumage ----------------------------------------------------------
    p("ENG-SPARK-PLUG", "Bougie d'allumage", "4.600000", "0.310000", "0.062000")
    p("ENG-IGNITION-COIL", "Bobine d'allumage double", "38.000000", "2.240000", "0.480000")
    p("ENG-HT-LEAD", "Câble haute tension", "7.200000", "0.340000", "0.074000")

    a("ENG-IGNITION-ASSY", "Circuit d'allumage", 12, {
        "ENG-SPARK-PLUG": 4, "ENG-IGNITION-COIL": 2, "ENG-HT-LEAD": 4,
        "ELE-SENSOR-KNOCK": 1, "ELE-SENSOR-CRANK": 1, "ELE-SENSOR-CAM": 1,
        "FIX-M6-16": 6,
    })

    # -- accessoires entraînés --------------------------------------------
    p("ALT-REGULATOR", "Régulateur d'alternateur", "14.000000", "0.920000", "0.064000")
    p("ALT-DIODE-BRIDGE", "Pont de diodes", "11.500000", "0.860000", "0.092000")
    p("ALT-BEARING", "Roulement d'alternateur", "4.200000", "0.340000", "0.048000")
    p("ALT-PULLEY", "Poulie d'alternateur", "9.800000", "0.720000", "0.310000")
    p("ENG-STARTER", "Démarreur", "96.000000", "9.400000", "3.100000")
    p("ENG-AC-COMPRESSOR", "Compresseur de climatisation", "168.000000", "14.600000", "5.400000")
    p("ENG-PS-PUMP", "Pompe de direction assistée", "112.000000", "8.800000", "3.600000")
    p("ENG-ACC-BELT", "Courroie d'accessoires", "16.400000", "0.940000", "0.260000")
    p("ENG-BELT-TENSIONER", "Tendeur de courroie d'accessoires", "34.000000", "2.180000", "0.420000")
    p("ENG-IDLER-PULLEY", "Galet d'accessoires", "14.200000", "1.040000", "0.240000")
    p("MOUNT-RUBBER", "Bloc élastomère de support", "8.900000", "0.520000", "0.340000")

    a("ALT-STATOR", "Stator d'alternateur", 18, {
        "MAT-COPPER-WIRE": "1.400000", "MAT-STEEL-SHEET": "0.900000",
    }, material="MAT-COPPER-WIRE")
    a("ALT-ROTOR", "Rotor d'alternateur", 16, {
        "MAT-COPPER-WIRE": "0.800000", "MAT-STEEL-BAR": "1.100000",
    }, material="MAT-COPPER-WIRE")
    a("ALT-HOUSING", "Carter d'alternateur", 10, {"MAT-ALU-CAST": "1.600000"},
      material="MAT-ALU-CAST")
    a("ENG-ALTERNATOR", "Alternateur", 22, {
        "ALT-STATOR": 1, "ALT-ROTOR": 1, "ALT-HOUSING": 1, "ALT-REGULATOR": 1,
        "ALT-DIODE-BRIDGE": 1, "ALT-BEARING": 2, "ALT-PULLEY": 1, "FIX-M6-25": 4,
    })
    a("ENG-ACC-BRACKET", "Patte de fixation d'accessoire", 8,
      {"MAT-STEEL-SHEET": "1.300000"}, material="MAT-STEEL-SHEET")
    a("ENG-ACCESSORY-ASSY", "Accessoires entraînés", 24, {
        "ENG-ALTERNATOR": 1, "ENG-STARTER": 1, "ENG-AC-COMPRESSOR": 1, "ENG-PS-PUMP": 1,
        "ENG-ACC-BELT": 1, "ENG-BELT-TENSIONER": 1, "ENG-IDLER-PULLEY": 2,
        "ENG-ACC-BRACKET": 3, "FIX-M10-40": 8, "FIX-M8-35": 6, "FIX-WASHER-10": 8,
    })

    # -- supports (montés 3 fois ici, 1 fois sous la transmission) --------
    a("MOUNT-BRACKET", "Support de groupe motopropulseur", 9,
      {"MAT-STEEL-SHEET": "1.800000"}, material="MAT-STEEL-SHEET")
    a("ENG-MOUNT-ASSY", "Support élastique complet", 6, {
        "MOUNT-BRACKET": 1, "MOUNT-RUBBER": 1, "FIX-M10-40": 2, "FIX-M12-60": 1,
    })

    a("GMP-ASSY", "Groupe motopropulseur", 95, {
        "ENG-BLOCK-ASSY": 1, "ENG-HEAD-ASSY": 1, "ENG-TIMING-ASSY": 1, "ENG-LUB-ASSY": 1,
        "ENG-COOL-ASSY": 1, "ENG-FUEL-ASSY": 1, "ENG-INTAKE-ASSY": 1,
        "ENG-EXHAUST-ASSY": 1, "ENG-IGNITION-ASSY": 1, "ENG-ACCESSORY-ASSY": 1,
        "ENG-MOUNT-ASSY": 3, "FIX-M10-40": 12, "FIX-M8-20": 16,
    })
