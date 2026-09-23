"""Électricité, électronique (ELE) et fluides de premier remplissage (FLU)."""

from __future__ import annotations

from .model import BomBuilder


def declare(b: BomBuilder) -> None:
    p = lambda ref, label, price, carbon, mass, unit="pce": b.purchased(  # noqa: E731
        ref, label, system="ELE", category="electrical",
        unit=unit, price=price, carbon=carbon, mass=mass,
    )
    a = lambda ref, label, labour, children, material=None: b.assembly(  # noqa: E731
        ref, label, system="ELE", category="electrical",
        labour=labour, children=children, material=material,
    )

    # -- composants partagés ----------------------------------------------
    p("ELE-CONNECTOR-2P", "Connecteur 2 voies", "1.400000", "0.096000", "0.008000")
    p("ELE-CONNECTOR-12P", "Connecteur 12 voies", "3.200000", "0.240000", "0.024000")
    p("ELE-CONNECTOR-40P", "Connecteur 40 voies", "8.600000", "0.640000", "0.086000")
    p("ELE-HARNESS-TAPE", "Ruban de faisceau", "2.800000", "0.140000", "0.062000")
    p("ELE-IC-CHIP", "Circuit intégré", "4.600000", "1.240000", "0.002000")
    p("ELE-PASSIVE-COMPONENT", "Composant passif", "0.120000", "0.018000", "0.000300")

    # -- alimentation ------------------------------------------------------
    p("ELE-BATTERY-TERMINAL", "Borne de batterie", "3.400000", "0.180000", "0.048000")
    p("ELE-CABLE-POSITIVE", "Câble de puissance positif", "16.800000", "1.240000", "0.620000")
    p("ELE-CABLE-GROUND", "Tresse de masse", "8.400000", "0.480000", "0.240000")
    p("ELE-FUSE-BLADE", "Fusible à lame", "0.340000", "0.024000", "0.002000")
    p("ELE-RELAY-4P", "Relais 4 broches", "3.800000", "0.280000", "0.034000")

    a("ELE-BATTERY", "Batterie 12 V", 16, {
        "MAT-LEAD-INGOT": "12.400000", "MAT-SULFURIC-ACID": "4.200000",
        "MAT-PP-GRANULE": "1.600000", "ELE-BATTERY-TERMINAL": 2,
    }, material="MAT-LEAD-INGOT")
    a("ELE-BATTERY-TRAY", "Bac de batterie", 6, {"MAT-STEEL-SHEET": "1.200000"},
      material="MAT-STEEL-SHEET")
    a("ELE-FUSE-BOX-HOUSING", "Boîtier de la platine à fusibles", 5,
      {"MAT-PA66-GRANULE": "0.600000"}, material="MAT-PA66-GRANULE")
    a("ELE-FUSE-BOX", "Platine à fusibles et relais", 14, {
        "ELE-FUSE-BOX-HOUSING": 1, "ELE-FUSE-BLADE": 20, "ELE-RELAY-4P": 6,
        "ELE-CONNECTOR-12P": 4,
    })

    # -- faisceaux ---------------------------------------------------------
    a("ELE-HARNESS-ENGINE", "Faisceau moteur", 38, {
        "MAT-COPPER-WIRE": "2.400000", "ELE-CONNECTOR-12P": 8, "ELE-CONNECTOR-2P": 14,
        "ELE-HARNESS-TAPE": 1, "FIX-CABLE-TIE-200": 24, "FIX-GROMMET-12": 6,
    }, material="MAT-COPPER-WIRE")
    a("ELE-HARNESS-DASH", "Faisceau de planche de bord", 34, {
        "MAT-COPPER-WIRE": "3.100000", "ELE-CONNECTOR-12P": 12, "ELE-CONNECTOR-2P": 10,
        "ELE-HARNESS-TAPE": 1, "FIX-CABLE-TIE-200": 20,
    }, material="MAT-COPPER-WIRE")
    # Monté dans chacune des quatre portes.
    a("ELE-HARNESS-DOOR", "Faisceau de porte", 12, {
        "MAT-COPPER-WIRE": "0.400000", "ELE-CONNECTOR-12P": 2, "ELE-CONNECTOR-2P": 3,
        "FIX-CABLE-TIE-200": 8, "FIX-GROMMET-12": 2,
    }, material="MAT-COPPER-WIRE")
    a("ELE-HARNESS-REAR", "Faisceau arrière", 22, {
        "MAT-COPPER-WIRE": "1.800000", "ELE-CONNECTOR-12P": 6, "ELE-CONNECTOR-2P": 8,
        "ELE-HARNESS-TAPE": 1, "FIX-CABLE-TIE-200": 16,
    }, material="MAT-COPPER-WIRE")

    # -- calculateurs : même carte et même boîtier pour les quatre ---------
    a("ELE-PCB", "Carte électronique équipée", 12, {
        "MAT-PCB-LAMINATE": "0.045000", "MAT-SOLDER-SAC": "0.020000",
        "ELE-IC-CHIP": 6, "ELE-PASSIVE-COMPONENT": 80,
    }, material="MAT-PCB-LAMINATE")
    a("ELE-ECU-HOUSING", "Boîtier de calculateur", 6, {"MAT-ALU-CAST": "0.380000"},
      material="MAT-ALU-CAST")
    a("ELE-ECU-ENGINE", "Calculateur moteur", 18, {
        "ELE-PCB": 1, "ELE-ECU-HOUSING": 1, "ELE-CONNECTOR-40P": 1,
    })
    a("ELE-ECU-ABS", "Calculateur ABS", 14, {
        "ELE-PCB": 1, "ELE-ECU-HOUSING": 1, "ELE-CONNECTOR-12P": 2,
    })
    a("ELE-ECU-AIRBAG", "Calculateur d'airbag", 14, {
        "ELE-PCB": 1, "ELE-ECU-HOUSING": 1, "ELE-CONNECTOR-12P": 2,
    })
    a("ELE-ECU-BODY", "Calculateur d'habitacle", 14, {
        "ELE-PCB": 1, "ELE-ECU-HOUSING": 1, "ELE-CONNECTOR-12P": 2,
    })

    # -- capteurs ----------------------------------------------------------
    p("ELE-SENSOR-COOLANT-TEMP", "Sonde de température d'eau", "9.400000", "0.480000", "0.042000")
    p("ELE-SENSOR-MAF", "Débitmètre d'air", "54.000000", "3.240000", "0.180000")
    p("ELE-SENSOR-MAP", "Capteur de pression d'admission", "21.000000", "1.180000", "0.064000")
    p("ELE-SENSOR-LAMBDA", "Sonde lambda", "46.000000", "2.840000", "0.120000")
    p("ELE-SENSOR-KNOCK", "Capteur de cliquetis", "24.000000", "1.240000", "0.058000")
    p("ELE-SENSOR-CRANK", "Capteur de position vilebrequin", "28.000000", "1.460000", "0.072000")
    p("ELE-SENSOR-CAM", "Capteur d'arbre à cames", "31.000000", "1.580000", "0.068000")
    p("ELE-SENSOR-ABS", "Capteur de roue ABS", "22.400000", "1.320000", "0.094000")

    # -- éclairage ---------------------------------------------------------
    p("ELE-REFLECTOR", "Réflecteur de projecteur", "14.200000", "0.960000", "0.240000")
    p("ELE-BULB-H4", "Lampe H4", "4.800000", "0.320000", "0.038000")
    p("ELE-BULB-W5W", "Lampe W5W", "0.900000", "0.064000", "0.004000")
    p("ELE-BULB-P21W", "Lampe P21W", "1.600000", "0.098000", "0.012000")
    p("ELE-LAMP-ADJUSTER", "Vis de réglage de projecteur", "3.400000", "0.180000", "0.024000")
    p("ELE-LENS-RED", "Glace de feu arrière", "12.600000", "0.840000", "0.320000")
    p("ELE-REPEATER", "Répétiteur latéral", "6.800000", "0.420000", "0.086000")
    p("ELE-LAMP-INTERIOR", "Plafonnier", "8.400000", "0.520000", "0.140000")
    p("ELE-PLATE-LAMP", "Éclaireur de plaque", "5.200000", "0.310000", "0.062000")
    p("ELE-THIRD-BRAKE-LAMP", "Troisième feu stop", "14.800000", "0.920000", "0.240000")
    p("ELE-FOG-LAMP", "Projecteur antibrouillard", "26.400000", "1.840000", "0.480000")

    a("ELE-LAMP-HOUSING", "Boîtier de feu", 6, {"MAT-PP-GRANULE": "0.700000"},
      material="MAT-PP-GRANULE")
    a("ELE-LAMP-LENS", "Glace de projecteur", 7, {"MAT-PC-GRANULE": "0.450000"},
      material="MAT-PC-GRANULE")
    a("ELE-HEADLAMP-ASSY", "Projecteur avant", 12, {
        "ELE-LAMP-HOUSING": 1, "ELE-LAMP-LENS": 1, "ELE-REFLECTOR": 1, "ELE-BULB-H4": 1,
        "ELE-BULB-W5W": 2, "ELE-LAMP-ADJUSTER": 2, "ELE-CONNECTOR-2P": 1,
        "FIX-SCREW-TORX-M5": 4,
    })
    a("ELE-TAIL-LAMP-ASSY", "Feu arrière", 8, {
        "ELE-LAMP-HOUSING": 1, "ELE-LENS-RED": 1, "ELE-BULB-P21W": 2, "ELE-BULB-W5W": 2,
        "ELE-CONNECTOR-2P": 1, "FIX-SCREW-TORX-M5": 4,
    })
    a("ELE-LIGHTING-ASSY", "Éclairage et signalisation", 18, {
        "ELE-HEADLAMP-ASSY": 2, "ELE-TAIL-LAMP-ASSY": 2, "ELE-REPEATER": 2,
        "ELE-LAMP-INTERIOR": 3, "ELE-PLATE-LAMP": 2, "ELE-THIRD-BRAKE-LAMP": 1,
        "FIX-SCREW-TORX-M5": 12,
    })

    # -- essuyage et multimédia -------------------------------------------
    p("ELE-WIPER-MOTOR", "Moteur d'essuie-glace avant", "42.000000", "3.180000", "1.640000")
    p("ELE-WIPER-REAR-MOTOR", "Moteur d'essuie-glace arrière", "32.000000", "2.480000", "1.180000")
    p("ELE-WIPER-LINKAGE", "Tringlerie d'essuyage", "24.600000", "1.840000", "1.240000")
    p("ELE-WIPER-ARM", "Bras d'essuie-glace", "9.800000", "0.640000", "0.280000")
    p("ELE-WIPER-BLADE", "Balai d'essuie-glace", "6.400000", "0.380000", "0.140000")
    p("ELE-WASHER-PUMP", "Pompe de lave-glace", "11.200000", "0.720000", "0.180000")
    p("ELE-WASHER-NOZZLE", "Gicleur de lave-glace", "3.600000", "0.190000", "0.024000")
    p("ELE-CLUSTER", "Combiné d'instruments", "84.000000", "6.240000", "1.420000")
    p("ELE-RADIO", "Autoradio", "96.000000", "7.480000", "1.860000")
    p("ELE-SPEAKER-100", "Haut-parleur 100 mm", "12.400000", "0.860000", "0.420000")
    p("ELE-ANTENNA", "Antenne de toit", "14.800000", "0.940000", "0.180000")
    p("ELE-ANTENNA-CABLE", "Câble d'antenne", "6.200000", "0.340000", "0.120000")
    p("ELE-HORN", "Avertisseur sonore", "13.600000", "0.980000", "0.480000")

    a("ELE-WASHER-TANK", "Réservoir de lave-glace", 6, {"MAT-HDPE-GRANULE": "0.800000"},
      material="MAT-HDPE-GRANULE")
    a("ELE-WIPER-ASSY", "Essuyage et lavage", 16, {
        "ELE-WIPER-MOTOR": 1, "ELE-WIPER-LINKAGE": 1, "ELE-WIPER-ARM": 2,
        "ELE-WIPER-BLADE": 2, "ELE-WASHER-PUMP": 1, "ELE-WASHER-TANK": 1,
        "ELE-WASHER-NOZZLE": 2, "FIX-M8-20": 6,
    })
    a("ELE-AUDIO-ASSY", "Réception radio", 10, {
        "ELE-ANTENNA": 1, "ELE-ANTENNA-CABLE": 1, "FIX-SCREW-TORX-M5": 4,
    })

    a("ELE-ASSY", "Électricité et électronique", 46, {
        "ELE-BATTERY": 1, "ELE-BATTERY-TRAY": 1, "ELE-CABLE-POSITIVE": 1,
        "ELE-CABLE-GROUND": 1, "ELE-FUSE-BOX": 1, "ELE-HARNESS-ENGINE": 1,
        "ELE-HARNESS-REAR": 1, "ELE-ECU-ENGINE": 1, "ELE-ECU-ABS": 1,
        "ELE-ECU-AIRBAG": 1, "ELE-ECU-BODY": 1, "ELE-LIGHTING-ASSY": 1,
        "ELE-WIPER-ASSY": 1, "ELE-AUDIO-ASSY": 1, "ELE-HORN": 1,
        "FIX-M8-20": 12, "FIX-CABLE-TIE-200": 30,
    })

    # -- fluides de premier remplissage -----------------------------------
    f = lambda ref, label, price, carbon, mass, unit="L": b.purchased(  # noqa: E731
        ref, label, system="FLU", category="fluid",
        unit=unit, price=price, carbon=carbon, mass=mass,
    )
    f("FLU-ENGINE-OIL", "Huile moteur 10W-40", "4.800000", "1.240000", "0.870000")
    f("FLU-COOLANT", "Liquide de refroidissement", "3.200000", "0.960000", "1.060000")
    f("FLU-BRAKE-FLUID", "Liquide de frein DOT4", "6.400000", "1.480000", "1.040000")
    f("FLU-PS-FLUID", "Fluide de direction assistée", "5.600000", "1.320000", "0.860000")
    f("FLU-WASHER-FLUID", "Liquide lave-glace", "1.200000", "0.340000", "0.980000")
    f("FLU-GEARBOX-OIL", "Huile de boîte 75W-80", "7.800000", "1.620000", "0.880000")
    f("FLU-AC-REFRIGERANT", "Fluide frigorigène R134a", "28.000000", "14.200000", "1.000000", "kg")
    f("FLU-GREASE", "Graisse multi-usage", "9.400000", "1.840000", "1.000000", "kg")

    b.assembly("FLU-ASSY", "Fluides de premier remplissage", system="FLU",
               category="fluid", labour=22, children={
                   "FLU-ENGINE-OIL": "4.200000", "FLU-COOLANT": "6.500000",
                   "FLU-BRAKE-FLUID": "0.900000", "FLU-PS-FLUID": "1.100000",
                   "FLU-WASHER-FLUID": "3.500000", "FLU-GEARBOX-OIL": "2.300000",
                   "FLU-AC-REFRIGERANT": "0.650000", "FLU-GREASE": "0.350000",
               })
