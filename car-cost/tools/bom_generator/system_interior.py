"""Intérieur (INT) : planche de bord, sièges, garnitures, sécurité, climatisation.

Le Multipla a six places individuelles : le même siège est monté six fois, trois
en rangée avant et trois en rangée arrière.
"""

from __future__ import annotations

from .model import BomBuilder


def declare(b: BomBuilder) -> None:
    p = lambda ref, label, price, carbon, mass: b.purchased(  # noqa: E731
        ref, label, system="INT", category="interior",
        unit="pce", price=price, carbon=carbon, mass=mass,
    )
    a = lambda ref, label, labour, children, material=None: b.assembly(  # noqa: E731
        ref, label, system="INT", category="interior",
        labour=labour, children=children, material=material,
    )

    # -- sièges ------------------------------------------------------------
    p("INT-SEAT-RAIL", "Glissière de siège", "16.800000", "1.240000", "1.180000")
    p("INT-SEAT-RECLINER", "Mécanisme d'inclinaison", "22.400000", "1.680000", "0.940000")
    p("INT-BELT-RETRACTOR", "Enrouleur de ceinture", "28.000000", "2.140000", "1.060000")
    p("INT-BELT-WEBBING", "Sangle de ceinture", "9.600000", "0.680000", "0.320000")
    p("INT-BELT-BUCKLE", "Boucle de ceinture", "12.400000", "0.920000", "0.280000")
    p("INT-BELT-ANCHOR", "Point d'ancrage de ceinture", "6.200000", "0.480000", "0.180000")

    a("INT-SEAT-FRAME", "Armature de siège", 22, {
        "MAT-STEEL-BAR": "4.800000", "MAT-STEEL-SHEET": "2.100000",
    }, material="MAT-STEEL-BAR")
    a("INT-SEAT-FOAM", "Mousse de siège", 6, {"MAT-FOAM-PU": "1.600000"},
      material="MAT-FOAM-PU")
    a("INT-SEAT-COVER", "Coiffe de siège", 12, {"MAT-FABRIC-PES": "1.400000"},
      material="MAT-FABRIC-PES")
    a("INT-HEADREST", "Appuie-tête", 7, {
        "MAT-FOAM-PU": "0.500000", "MAT-FABRIC-PES": "0.350000",
    }, material="MAT-FOAM-PU")
    a("INT-SEATBELT-ASSY", "Ceinture de sécurité complète", 9, {
        "INT-BELT-RETRACTOR": 1, "INT-BELT-WEBBING": 1, "INT-BELT-BUCKLE": 1,
        "INT-BELT-ANCHOR": 2, "FIX-M12-60": 2,
    })
    a("INT-SEAT-ASSY", "Siège individuel complet", 26, {
        "INT-SEAT-FRAME": 1, "INT-SEAT-FOAM": 2, "INT-SEAT-COVER": 2, "INT-HEADREST": 1,
        "INT-SEAT-RAIL": 2, "INT-SEAT-RECLINER": 1, "INT-SEATBELT-ASSY": 1,
        "FIX-M10-40": 4,
    })
    a("INT-SEAT-CROSSMEMBER", "Traverse de fixation de rangée", 9,
      {"MAT-STEEL-SHEET": "2.800000"}, material="MAT-STEEL-SHEET")
    a("INT-ROW-FRONT", "Rangée avant trois places", 14, {
        "INT-SEAT-ASSY": 3, "INT-SEAT-CROSSMEMBER": 1, "FIX-M10-40": 8,
    })
    a("INT-ROW-REAR", "Rangée arrière trois places", 12, {
        "INT-SEAT-ASSY": 3, "INT-SEAT-CROSSMEMBER": 1, "FIX-M10-40": 8,
    })

    # -- planche de bord ---------------------------------------------------
    p("INT-AIR-VENT", "Aérateur", "8.400000", "0.420000", "0.140000")
    p("INT-STEERING-WHEEL", "Volant", "42.000000", "3.180000", "2.240000")
    p("INT-AIRBAG-DRIVER", "Coussin gonflable conducteur", "96.000000", "6.840000", "1.620000")
    p("INT-AIRBAG-PASSENGER", "Coussin gonflable passager", "112.000000", "7.920000", "2.180000")
    p("INT-SWITCH-PANEL", "Bloc de commandes", "24.600000", "1.640000", "0.420000")

    a("INT-DASH-CARRIER", "Traverse de planche de bord", 18,
      {"MAT-STEEL-SHEET": "5.400000"}, material="MAT-STEEL-SHEET")
    a("INT-DASH-UPPER", "Peau de planche de bord", 14, {"MAT-PP-GRANULE": "3.200000"},
      material="MAT-PP-GRANULE")
    a("INT-GLOVE-BOX", "Boîte à gants", 8, {"MAT-PP-GRANULE": "1.100000"},
      material="MAT-PP-GRANULE")
    a("INT-CENTER-CONSOLE", "Console centrale", 10, {"MAT-PP-GRANULE": "1.800000"},
      material="MAT-PP-GRANULE")
    a("INT-DASH-ASSY", "Planche de bord équipée", 42, {
        "INT-DASH-CARRIER": 1, "INT-DASH-UPPER": 1, "INT-GLOVE-BOX": 1,
        "INT-CENTER-CONSOLE": 1, "INT-AIR-VENT": 4, "INT-STEERING-WHEEL": 1,
        "INT-AIRBAG-DRIVER": 1, "INT-AIRBAG-PASSENGER": 1, "INT-SWITCH-PANEL": 1,
        "ELE-CLUSTER": 1, "ELE-RADIO": 1, "ELE-HARNESS-DASH": 1,
        "FIX-M8-20": 10, "FIX-SCREW-TORX-M5": 16, "FIX-NUT-M6": 6,
    })

    # -- garnitures --------------------------------------------------------
    p("INT-MIRROR-INT", "Rétroviseur intérieur", "12.800000", "0.840000", "0.320000")
    p("INT-SUN-VISOR", "Pare-soleil", "9.400000", "0.560000", "0.240000")
    p("INT-GRAB-HANDLE", "Poignée de maintien", "5.600000", "0.320000", "0.120000")

    a("INT-HEADLINER", "Ciel de toit", 14, {
        "MAT-FABRIC-PES": "3.400000", "MAT-FOAM-PU": "0.900000",
    }, material="MAT-FABRIC-PES")
    a("INT-CARPET", "Moquette", 12, {
        "MAT-CARPET-FELT": "5.600000", "MAT-BITUMEN-PAD": "2.200000",
    }, material="MAT-CARPET-FELT")
    a("INT-PILLAR-TRIM", "Garniture de pied", 4, {"MAT-ABS-GRANULE": "0.400000"},
      material="MAT-ABS-GRANULE")
    a("INT-SILL-TRIM", "Garniture de bas de caisse", 4, {"MAT-ABS-GRANULE": "0.500000"},
      material="MAT-ABS-GRANULE")
    a("INT-PARCEL-SHELF", "Tablette arrière", 8, {
        "MAT-ABS-GRANULE": "1.200000", "MAT-FABRIC-PES": "0.500000",
    }, material="MAT-ABS-GRANULE")
    a("INT-DOOR-PANEL-FRONT", "Panneau de porte avant", 12, {
        "MAT-ABS-GRANULE": "1.600000", "MAT-FABRIC-PES": "0.700000",
        "MAT-LEATHERETTE": "0.320000",
    }, material="MAT-ABS-GRANULE")
    a("INT-DOOR-PANEL-REAR", "Panneau de porte arrière", 11, {
        "MAT-ABS-GRANULE": "1.400000", "MAT-FABRIC-PES": "0.600000",
    }, material="MAT-ABS-GRANULE")
    a("INT-TRIM-ASSY", "Garnitures intérieures", 34, {
        "INT-HEADLINER": 1, "INT-CARPET": 1, "INT-PILLAR-TRIM": 6, "INT-SILL-TRIM": 4,
        "INT-PARCEL-SHELF": 1, "FIX-CLIP-PLASTIC": 40,
    })

    # -- climatisation -----------------------------------------------------
    p("INT-BLOWER-MOTOR", "Pulseur d'habitacle", "38.000000", "2.640000", "1.240000")
    p("INT-EVAPORATOR", "Évaporateur", "46.000000", "4.180000", "1.860000")
    p("INT-HEATER-CORE", "Radiateur de chauffage", "32.000000", "3.240000", "1.420000")
    p("INT-EXPANSION-VALVE", "Détendeur", "18.400000", "1.180000", "0.240000")
    p("INT-AC-LINE", "Canalisation de climatisation", "22.600000", "1.640000", "0.680000")
    p("INT-CONDENSER", "Condenseur de climatisation", "52.000000", "4.860000", "2.240000")
    p("INT-CABIN-FILTER", "Filtre d'habitacle", "8.600000", "0.480000", "0.180000")
    p("INT-HVAC-CONTROL", "Commande de climatisation", "26.400000", "1.840000", "0.420000")
    p("INT-HVAC-ACTUATOR", "Actionneur de volet", "12.800000", "0.920000", "0.160000")

    a("INT-HVAC-HOUSING", "Boîtier de climatisation", 12, {"MAT-PP-GRANULE": "2.400000"},
      material="MAT-PP-GRANULE")
    a("INT-HVAC-ASSY", "Climatisation et chauffage", 32, {
        "INT-HVAC-HOUSING": 1, "INT-BLOWER-MOTOR": 1, "INT-EVAPORATOR": 1,
        "INT-HEATER-CORE": 1, "INT-EXPANSION-VALVE": 1, "INT-AC-LINE": 2,
        "INT-CONDENSER": 1, "INT-CABIN-FILTER": 1, "INT-HVAC-CONTROL": 1,
        "INT-HVAC-ACTUATOR": 3, "FIX-M6-16": 12,
    })

    a("INT-ASSY", "Intérieur", 60, {
        "INT-DASH-ASSY": 1, "INT-ROW-FRONT": 1, "INT-ROW-REAR": 1, "INT-TRIM-ASSY": 1,
        "INT-HVAC-ASSY": 1, "INT-MIRROR-INT": 1, "INT-SUN-VISOR": 2,
        "INT-GRAB-HANDLE": 4, "FIX-M8-20": 16, "FIX-SCREW-TORX-M5": 20,
    })
