"""Matières premières et visserie : les deux réservoirs partagés par tout le reste.

Ces pièces sont employées par des dizaines de parents. C'est d'elles que vient
l'essentiel du partage « en bas » du graphe, celui qui fait qu'une nomenclature
n'est pas un arbre.
"""

from __future__ import annotations

from .model import BomBuilder


def declare(b: BomBuilder) -> None:
    mat = lambda ref, label, unit, price, carbon, mass: b.purchased(  # noqa: E731
        ref, label, system="MAT", category="material",
        unit=unit, price=price, carbon=carbon, mass=mass,
    )

    # -- métaux ------------------------------------------------------------
    mat("MAT-CAST-IRON", "Fonte grise GJL-250", "kg", "0.850000", "1.900000", "1.000000")
    mat("MAT-STEEL-SHEET", "Tôle acier DC04", "kg", "1.100000", "2.100000", "1.000000")
    mat("MAT-STEEL-BAR", "Barre acier 42CrMo4", "kg", "1.250000", "2.200000", "1.000000")
    mat("MAT-STEEL-SPRING", "Fil acier à ressort", "kg", "1.850000", "2.400000", "1.000000")
    mat("MAT-STAINLESS-SHEET", "Tôle inox 409", "kg", "3.400000", "4.500000", "1.000000")
    mat("MAT-ALU-CAST", "Alliage aluminium de fonderie", "kg", "2.600000", "8.600000", "1.000000")
    mat("MAT-ALU-SHEET", "Tôle aluminium 5754", "kg", "3.100000", "9.200000", "1.000000")
    mat("MAT-COPPER-WIRE", "Fil de cuivre émaillé", "kg", "8.400000", "4.200000", "1.000000")
    mat("MAT-BRASS-BAR", "Barre de laiton", "kg", "6.900000", "3.800000", "1.000000")
    mat("MAT-ZINC-COATING", "Revêtement zinc", "kg", "3.200000", "3.500000", "1.000000")
    mat("MAT-LEAD-INGOT", "Lingot de plomb", "kg", "2.100000", "1.600000", "1.000000")
    mat("MAT-WELD-WIRE", "Fil de soudure MAG", "kg", "2.300000", "2.500000", "1.000000")

    # -- polymères ---------------------------------------------------------
    mat("MAT-PP-GRANULE", "Granulé polypropylène", "kg", "1.450000", "1.900000", "1.000000")
    mat("MAT-ABS-GRANULE", "Granulé ABS", "kg", "2.050000", "3.100000", "1.000000")
    mat("MAT-PA66-GRANULE", "Granulé polyamide 6.6", "kg", "3.600000", "6.400000", "1.000000")
    mat("MAT-PC-GRANULE", "Granulé polycarbonate", "kg", "3.900000", "5.500000", "1.000000")
    mat("MAT-HDPE-GRANULE", "Granulé polyéthylène HD", "kg", "1.350000", "1.800000", "1.000000")
    mat("MAT-EPDM-RUBBER", "Caoutchouc EPDM", "kg", "2.400000", "2.800000", "1.000000")
    mat("MAT-NBR-RUBBER", "Caoutchouc nitrile", "kg", "3.100000", "3.200000", "1.000000")
    mat("MAT-FOAM-PU", "Mousse polyuréthane", "kg", "4.200000", "5.800000", "1.000000")
    mat("MAT-GLASS-FIBER", "Fibre de verre de renfort", "kg", "2.800000", "2.600000", "1.000000")

    # -- verre, textiles, chimie ------------------------------------------
    mat("MAT-GLASS-FLOAT", "Verre float", "kg", "0.950000", "1.200000", "1.000000")
    mat("MAT-FABRIC-PES", "Tissu polyester", "m2", "6.500000", "5.200000", "0.420000")
    mat("MAT-CARPET-FELT", "Feutre de moquette", "m2", "4.100000", "3.400000", "0.900000")
    mat("MAT-LEATHERETTE", "Simili cuir", "m2", "9.800000", "7.100000", "0.550000")
    mat("MAT-BITUMEN-PAD", "Plaque bitume insonorisante", "kg", "1.600000", "1.400000", "1.000000")
    mat("MAT-PAINT-PRIMER", "Apprêt", "L", "7.500000", "4.600000", "1.250000")
    mat("MAT-PAINT-BASE", "Base colorée", "L", "12.400000", "5.300000", "1.100000")
    mat("MAT-PAINT-CLEAR", "Vernis", "L", "14.200000", "5.900000", "1.050000")
    mat("MAT-ADHESIVE-PU", "Colle polyuréthane", "kg", "8.600000", "3.900000", "1.000000")
    mat("MAT-SULFURIC-ACID", "Acide sulfurique dilué", "L", "0.900000", "0.600000", "1.300000")

    # -- électronique et catalyse -----------------------------------------
    mat("MAT-SOLDER-SAC", "Alliage de brasage SAC305", "kg", "26.000000", "12.000000", "1.000000")
    mat("MAT-PCB-LAMINATE", "Stratifié FR-4", "m2", "42.000000", "28.000000", "2.300000")
    mat("MAT-CERAMIC-ALO", "Support céramique cordiérite", "kg", "11.500000", "9.400000", "1.000000")
    mat("MAT-PGM-CATALYST", "Métaux précieux de catalyse", "g", "38.000000", "0.210000", "0.001000")

    # -- visserie et fixations (prix pour 100 pièces) ----------------------
    fix = lambda ref, label, price, carbon, mass: b.purchased(  # noqa: E731
        ref, label, system="FIX", category="fastener",
        unit="pce", price=price, carbon=carbon, mass=mass, per=100,
    )

    fix("FIX-M6-16", "Vis M6×16", "3.900000", "0.001300", "0.004000")
    fix("FIX-M6-25", "Vis M6×25", "4.400000", "0.001600", "0.005000")
    fix("FIX-M8-20", "Vis M8×20", "6.200000", "0.002400", "0.009000")
    fix("FIX-M8-35", "Vis M8×35", "7.800000", "0.003100", "0.012000")
    fix("FIX-M10-40", "Vis M10×40", "12.500000", "0.005200", "0.022000")
    fix("FIX-M12-60", "Vis M12×60", "22.000000", "0.009800", "0.045000")
    fix("FIX-NUT-M6", "Écrou M6", "2.100000", "0.000800", "0.002000")
    fix("FIX-NUT-M8", "Écrou M8", "3.000000", "0.001200", "0.004000")
    fix("FIX-NUT-M10", "Écrou M10", "4.600000", "0.001900", "0.008000")
    fix("FIX-WASHER-6", "Rondelle Ø6", "0.900000", "0.000400", "0.001000")
    fix("FIX-WASHER-8", "Rondelle Ø8", "1.200000", "0.000500", "0.002000")
    fix("FIX-WASHER-10", "Rondelle Ø10", "1.700000", "0.000700", "0.003000")
    fix("FIX-CLIP-PLASTIC", "Agrafe plastique", "1.800000", "0.000600", "0.002000")
    fix("FIX-RIVET-4", "Rivet aveugle Ø4", "1.400000", "0.000500", "0.001000")
    fix("FIX-CIRCLIP-20", "Circlip Ø20", "2.600000", "0.000900", "0.002000")
    fix("FIX-HOSE-CLAMP-25", "Collier de serrage Ø25", "9.500000", "0.003400", "0.011000")
    fix("FIX-HOSE-CLAMP-40", "Collier de serrage Ø40", "12.000000", "0.004200", "0.016000")
    fix("FIX-STUD-M8", "Goujon M8", "8.400000", "0.003300", "0.013000")
    fix("FIX-SCREW-TORX-M5", "Vis Torx M5", "3.200000", "0.001100", "0.003000")
    fix("FIX-SPRING-PIN-6", "Goupille élastique Ø6", "2.200000", "0.000800", "0.002000")
    fix("FIX-GROMMET-12", "Passe-fil Ø12", "2.900000", "0.001000", "0.003000")
    fix("FIX-CABLE-TIE-200", "Collier de câblage 200 mm", "1.100000", "0.000400", "0.001000")
    fix("FIX-WELD-NUT-M8", "Écrou à souder M8", "3.600000", "0.001400", "0.005000")
    fix("FIX-BOLT-WHEEL-M12", "Boulon de roue M12", "34.000000", "0.014000", "0.062000")
    fix("FIX-NUT-EXHAUST-M8", "Écrou cuivré M8 échappement", "5.100000", "0.002000", "0.006000")
