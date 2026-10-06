"""Où poser chaque pavé de la maquette du Multipla. Table relue à la main.

Repère glTF, en mètres : X vers la gauche, Y vers le haut, Z vers l'avant. La
caisse va de Z = -2,0 (hayon) à Z = +2,0 (pare-chocs avant), X de ±0,94, et
le sol est à Y = 0.

Chaque pièce donne ses côtés (X, Y, Z) et le centre de chaque emplacement de
montage. Le côté `None` est l'épaisseur : le générateur la calcule pour que la
masse mesurée vaille la quantité de matière de la nomenclature (R1). Les
autres côtés sont des ordres de grandeur plausibles, pas des cotes réelles :
la maquette est synthétique.
"""

FRONT_WHEELS, REAR_WHEELS = 1.33, -1.33
FRONT_DOOR, REAR_DOOR = 0.55, -0.45

PIECES = {
    # Structure
    "CAR-PANEL-FLOOR": ((1.60, None, 3.20), [(0, 0.30, 0)]),
    "CAR-PANEL-ROOF": ((1.60, None, 2.30), [(0, 1.66, -0.35)]),
    "CAR-PANEL-SIDE": ((None, 1.20, 1.90), [(x, 0.95, -0.85) for x in (0.90, -0.90)]),
    "CAR-BULKHEAD": ((1.60, 0.50, None), [(0, 0.75, 1.10)]),
    "CAR-COWL": ((1.60, None, 0.20), [(0, 1.00, 1.05)]),
    "CAR-PILLAR-A": ((None, 0.55, 0.10), [(x, 1.33, 0.95) for x in (0.89, -0.89)]),
    "CAR-PILLAR-B": ((None, 0.55, 0.10), [(x, 1.33, 0.00) for x in (0.89, -0.89)]),
    "CAR-PILLAR-C": ((None, 0.55, 0.10), [(x, 1.33, -1.40) for x in (0.89, -0.89)]),
    "CAR-RAIL-FRONT": ((None, 0.12, 1.00), [(x, 0.42, 1.40) for x in (0.45, -0.45)]),
    "CAR-RAIL-REAR": ((None, 0.12, 0.90), [(x, 0.42, -1.45) for x in (0.50, -0.50)]),
    "CAR-WHEEL-ARCH": (
        (None, 0.45, 0.75),
        [(x, 0.55, z) for z in (FRONT_WHEELS, REAR_WHEELS) for x in (0.75, -0.75)],
    ),
    # Ouvrants
    "CAR-HOOD-SHELL": ((1.60, None, 0.80), [(0, 0.95, 1.55)]),
    "CAR-DOOR-SHELL-FRONT": ((None, 0.75, 1.00), [(x, 0.80, FRONT_DOOR) for x in (0.935, -0.935)]),
    "CAR-DOOR-SHELL-REAR": ((None, 0.75, 0.95), [(x, 0.80, REAR_DOOR) for x in (0.935, -0.935)]),
    "CAR-TAILGATE-SHELL": ((1.40, 0.60, None), [(0, 0.80, -2.00)]),
    "CAR-DOOR-SEAL": (
        (None, 1.00, 0.03),
        [(x, 0.95, z) for z in (0.03, -0.95) for x in (0.94, -0.94)] + [(0.70, 1.00, -2.00)],
    ),
    # Vitrage
    "CAR-GLASS-QUARTER": ((None, 0.45, 0.50), [(x, 1.35, -1.65) for x in (0.91, -0.91)]),
    "CAR-GLASS-TAILGATE": ((1.30, 0.60, None), [(0, 1.35, -1.98)]),
    # Pare-chocs et garnitures extérieures
    "CAR-BUMPER-BEAM": ((1.50, 0.12, None), [(0, 0.45, z) for z in (1.90, -1.90)]),
    "CAR-BUMPER-SKIN-FRONT": ((1.80, 0.35, None), [(0, 0.45, 1.98)]),
    "CAR-BUMPER-SKIN-REAR": ((1.80, 0.35, None), [(0, 0.45, -1.98)]),
    "CAR-GRILLE": ((1.00, 0.15, None), [(0, 0.78, 1.97)]),
    "CAR-ARCH-TRIM": (
        (None, 0.08, 0.80),
        [(x, 0.80, z) for z in (FRONT_WHEELS, REAR_WHEELS) for x in (0.945, -0.945)],
    ),
    # Habillage et faisceaux de porte
    "INT-DOOR-PANEL-FRONT": ((None, 0.60, 0.90), [(x, 0.80, FRONT_DOOR) for x in (0.89, -0.89)]),
    "INT-DOOR-PANEL-REAR": ((None, 0.60, 0.85), [(x, 0.80, REAR_DOOR) for x in (0.89, -0.89)]),
    "ELE-HARNESS-DOOR": (
        (None, 0.015, 0.60),
        [(x, 0.95, z) for z in (FRONT_DOOR, REAR_DOOR) for x in (0.91, -0.91)],
    ),
}

# Décor : sans `extras.carcost`, ignoré à l'import. Le Multipla se reconnaît à
# ses deux étages d'optiques avant, l'un au pied du pare-brise.
DECOR = {
    "Pare-brise": ((1.50, 0.70, 0.006), [(0, 1.35, 1.00)]),
    "Rétroviseur": ((0.06, 0.12, 0.18), [(x, 1.15, 0.95) for x in (1.00, -1.00)]),
    "Optique basse": ((0.30, 0.12, 0.05), [(x, 0.75, 1.97) for x in (0.65, -0.65)]),
    "Optique haute": ((0.25, 0.08, 0.05), [(x, 1.08, 1.12) for x in (0.55, -0.55)]),
    "Feu arrière": ((0.12, 0.40, 0.05), [(x, 1.05, -2.02) for x in (0.80, -0.80)]),
    "Roue": (
        (0.20, 0.60, 0.60),
        [(x, 0.30, z) for z in (FRONT_WHEELS, REAR_WHEELS) for x in (0.80, -0.80)],
    ),
}
