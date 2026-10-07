"""Formes de la maquette du Multipla, stylisée. Table relue à la main.

Repère glTF, en mètres : X vers la gauche, Y vers le haut, Z vers l'avant. Le
sol est à Y = 0, la caisse va d'environ Z = -2,03 (pare-chocs arrière) à Z = +2,03 (avant).

Une forme est un polygone 2D extrudé, centré : `(polygone, largeur, axe)`,
plus un galbe facultatif : le décalage du milieu de la largeur dans le plan du
polygone (les bords ne bougent pas). Flancs et portes sont des tôles
`("sheet", colonnes, t)` : une grille (z, y) d'épaisseur t selon X, bombée vers
+X par `flank(y)` ; leur emplacement de droite reçoit le maillage miroir
(MIRRORED).
L'axe d'extrusion fixe le plan du polygone : « x » → (z, y), vue de profil ;
« y » → (x, z), vue de dessus ; « z » → (x, y), vue de face. Chaque pièce
donne sa forme en fonction d'une épaisseur t, et la translation de chaque
emplacement de montage : le générateur cherche t pour que la masse mesurée
vaille la quantité de matière de la nomenclature (R1). Les autres paires
gauche et droite partagent une forme symétrique, posée par translation.
Cotes plausibles, pas constructeur : la maquette est synthétique.
"""

import math
from fractions import Fraction


def strip(points, t):
    """Bande d'épaisseur t le long d'une polyligne, à gauche du sens de parcours."""
    normals = []
    for (a0, b0), (a1, b1) in zip(points, points[1:]):
        length = math.sqrt((a1 - a0) * (a1 - a0) + (b1 - b0) * (b1 - b0))
        normals.append(((b0 - b1) / length, (a1 - a0) / length))
    offset = []
    for i, (a, b) in enumerate(points):
        (u0, v0), (u1, v1) = normals[max(i - 1, 0)], normals[min(i, len(normals) - 1)]
        scale = t / (1 + u0 * u1 + v0 * v1)  # onglet : épaisseur constante aux coudes
        offset.append((a + (u0 + u1) * scale, b + (v0 + v1) * scale))
    return list(points) + offset[::-1]


def turn(angle):
    """(cos, sin) de `angle` × π, angle rationnel ≤ 2 : série de Taylor en Fraction,
    arrondie une fois. Même résultat sur toute plateforme, alors que
    le cosinus de la libm varie selon la plateforme et casserait le `--check` octet pour octet."""
    x, term, c, s = Fraction(math.pi) * angle, Fraction(1), Fraction(0), Fraction(0)
    for i in range(60):  # dernier terme < 10⁻³⁰ pour |x| ≤ 2π
        if i % 2:
            s += (1, 1, -1, -1)[i % 4] * term
        else:
            c += (1, 1, -1, -1)[i % 4] * term
        term = term * x / (i + 1)
    return float(c), float(s)


def arc(r, n=10):
    """Demi-cercle supérieur, de θ = 0 (avant) à θ = π (arrière)."""
    return [(r * c, r * s) for c, s in (turn(Fraction(k, n)) for k in range(n + 1))]


def ellipse(ra, rb, n=20):
    """Sommets décalés d'un demi-pas : aucun ne tombe sur un axe (roue posée au-dessus du sol)."""
    return [(ra * c, rb * s) for c, s in (turn(Fraction(2 * k + 1, n)) for k in range(n))]


def rectangle(a, b):
    return [(-a / 2, -b / 2), (a / 2, -b / 2), (a / 2, b / 2), (-a / 2, b / 2)]


WHEEL_Z, WHEEL_Y, CUTOUT = 1.33, 0.31, 0.46
ARCH_Y = 0.22  # centre des découpes au ras du bas de caisse : le cercle le rejoint sans marche


def along(points, z):
    """Ordonnée en z de la ligne brisée `points`, aux z croissants."""
    for (z0, y0), (z1, y1) in zip(points, points[1:]):
        if z0 <= z <= z1:
            return y0 + (y1 - y0) * (z - z0) / (z1 - z0)
    raise ValueError(f"z = {z} hors de la ligne")


def flank(y):
    """Galbe des flancs et des portes vers l'extérieur : 3 cm à mi-hauteur, bords adoucis."""
    u = max(-1.0, min(1.0, (y - 0.64) / 0.42))
    return 0.03 * (1 - u * u * u * u)


# Profil latéral (z, y) : ceinture qui suit le capot, marche au pied du
# pare-brise, ceinture basse, chute du hayon ; bas de caisse creusé des
# passages de roue.
BELT = [(-1.97, 0.98), (-1.94, 1.02), (1.23, 1.06), (1.30, 0.90), (1.50, 0.89), (1.70, 0.865),
        (1.88, 0.83), (1.96, 0.795)]
SILL = [(-1.97, 0.32), (-1.80, 0.22), (1.80, 0.22), (1.96, 0.32)]
DOOR_SILL = [(0.03, 0.30), (0.08, 0.24), (0.81, 0.24), (0.86, 0.30)]


def sill(z):
    y = along(SILL, z)
    for zc in (WHEEL_Z, -WHEEL_Z):
        if abs(z - zc) < CUTOUT:
            y = max(y, ARCH_Y + math.sqrt(CUTOUT * CUTOUT - (z - zc) * (z - zc)))
    return y


def columns(z0, z1, bottom, top, breaks):
    """Colonnes (z, bas, haut) d'une tôle de flanc : tous les 10 cm, aux cassures
    des profils et le long des passages de roue."""
    zs = {round(z0 + k * 0.1, 6) for k in range(int((z1 - z0) / 0.1) + 1)} | {z1, *breaks}
    zs |= {round(zc + CUTOUT * turn(Fraction(k, 12))[0], 6) for zc in (WHEEL_Z, -WHEEL_Z)
           for k in range(13)}
    return [(z, bottom(z), top(z)) for z in sorted(zs) if z0 <= z <= z1]


SIDE = columns(-1.97, 1.96, sill, lambda z: along(BELT, z), [z for z, _ in BELT + SILL])
FRONT_DOOR = columns(0.03, 0.86, lambda z: along(DOOR_SILL, z), lambda z: 1.02,
                     [z for z, _ in DOOR_SILL])
REAR_DOOR = [(-z, low, high) for z, low, high in reversed(FRONT_DOOR)]
HOOD = [(1.99, 0.78), (1.88, 0.83), (1.70, 0.865), (1.50, 0.89), (1.30, 0.90)]
COWL = [(1.30, 0.90), (1.27, 0.98), (1.24, 1.06), (1.14, 1.07)]  # la marche
WINDSCREEN = [(1.15, 1.07), (0.38, 1.62)]
ROOF = [(0.40, 1.625), (0.10, 1.66), (-0.60, 1.67), (-1.50, 1.665), (-1.90, 1.645), (-1.96, 1.60)]
FRONT_BUMPER = [(0.955, 1.72), (0.95, 1.88), (0.87, 1.975), (0.70, 1.99),
                (-0.70, 1.99), (-0.87, 1.975), (-0.95, 1.88), (-0.955, 1.72)]  # (x, z)


def sides(x, y=0, z=0):
    return [(x, y, z), (-x, y, z)]


def at_wheels(x, y=WHEEL_Y):
    return [(s, y, z) for z in (WHEEL_Z, -WHEEL_Z) for s in (x, -x)]


PIECES = {
    # Structure
    "CAR-PANEL-FLOOR": (lambda t: (rectangle(1.60, 2.90), t, "y"), [(0, 0.26, -0.30)]),
    "CAR-PANEL-ROOF": (lambda t: (strip(ROOF, t), 1.84, "x", (0, 0.06)), [(0, 0, 0)]),
    "CAR-PANEL-SIDE": (lambda t: ("sheet", SIDE, t), sides(0.92)),
    "CAR-BULKHEAD": (lambda t: (rectangle(1.60, 0.53), t, "z"), [(0, 0.60, 1.20)]),
    "CAR-COWL": (lambda t: (strip(COWL, t), 1.84, "x", (0, 0.05)), [(0, 0, 0)]),
    "CAR-PILLAR-A": (lambda t: (strip([(1.14, 1.06), (0.38, 1.62)], 0.07), t, "x"), sides(0.916)),
    "CAR-PILLAR-B": (lambda t: (strip([(0.03, 1.02), (0.0, 1.66)], 0.08), t, "x"), sides(0.916)),
    "CAR-PILLAR-C": (lambda t: (strip([(-1.36, 1.02), (-1.40, 1.66)], 0.08), t, "x"), sides(0.916)),
    "CAR-RAIL-FRONT": (lambda t: (rectangle(1.00, 0.12), t, "x"), sides(0.45, 0.42, 1.40)),
    "CAR-RAIL-REAR": (lambda t: (rectangle(0.90, 0.12), t, "x"), sides(0.50, 0.42, -1.45)),
    "CAR-WHEEL-ARCH": (lambda t: (strip(arc(0.48), t), 0.26, "x"), at_wheels(0.79, ARCH_Y)),
    # Ouvrants
    "CAR-HOOD-SHELL": (lambda t: (strip(HOOD, t), 1.84, "x", (0, 0.05)), [(0, 0, 0)]),
    "CAR-DOOR-SHELL-FRONT": (lambda t: ("sheet", FRONT_DOOR, t), sides(0.930)),
    "CAR-DOOR-SHELL-REAR": (lambda t: ("sheet", REAR_DOOR, t), sides(0.930)),
    "CAR-TAILGATE-SHELL": (
        lambda t: (strip([(-1.965, 1.02), (-1.975, 0.80), (-1.985, 0.60)], t), 1.80, "x",
                    (-0.04, 0)),
        [(0, 0, 0)],
    ),
    "CAR-DOOR-SEAL": (
        lambda t: (rectangle(0.03, 0.72), t, "x"),
        sides(0.895, 0.64, 0.845) + sides(0.895, 0.64, -0.845) + [(0.70, 0.62, -1.94)],
    ),
    # Vitrage
    "CAR-GLASS-QUARTER": (
        lambda t: ([(-1.44, 1.03), (-1.93, 1.03), (-1.94, 1.615), (-1.90, 1.645), (-1.44, 1.665)], t, "x"),
        sides(0.910),
    ),
    "CAR-GLASS-TAILGATE": (lambda t: (strip([(-1.955, 1.60), (-1.965, 1.03)], t), 1.80, "x",
                                      (-0.04, 0)),
                           [(0, 0, 0)]),
    # Pare-chocs et garnitures extérieures
    "CAR-BUMPER-BEAM": (lambda t: (rectangle(1.50, 0.12), t, "z"), [(0, 0.42, 1.90), (0, 0.42, -1.90)]),
    "CAR-BUMPER-SKIN-FRONT": (lambda t: (strip(FRONT_BUMPER, t), 0.40, "y", (0, 0.04)),
                              [(0, 0.42, 0)]),
    "CAR-BUMPER-SKIN-REAR": (  # le même tracé tourné d'un demi-tour autour de Y
        lambda t: (strip([(-x, -z) for x, z in FRONT_BUMPER], t), 0.40, "y", (0, -0.04)),
        [(0, 0.42, 0)],
    ),
    "CAR-GRILLE": (
        lambda t: ([(-0.48, -0.07), (0.48, -0.07), (0.50, 0), (0.48, 0.07), (-0.48, 0.07), (-0.50, 0)],
                   t, "z"),
        [(0, 0.70, 1.975)],
    ),
    "CAR-ARCH-TRIM": (lambda t: (strip(arc(0.52), 0.06), t, "x"), at_wheels(0.955, ARCH_Y)),
    # Habillage et faisceaux de porte
    "INT-DOOR-PANEL-FRONT": (lambda t: (rectangle(0.78, 0.62), t, "x"), sides(0.89, 0.64, 0.46)),
    "INT-DOOR-PANEL-REAR": (lambda t: (rectangle(0.76, 0.62), t, "x"), sides(0.89, 0.64, -0.46)),
    "ELE-HARNESS-DOOR": (
        lambda t: (rectangle(0.60, 0.015), t, "x"),
        sides(0.905, 0.95, 0.485) + sides(0.905, 0.95, -0.485),
    ),
}

MIRRORED = {"CAR-PANEL-SIDE", "CAR-DOOR-SHELL-FRONT", "CAR-DOOR-SHELL-REAR"}

# Décor : sans `extras.carcost`, ignoré à l'import. Nom → (forme, matériau,
# translations). Le Multipla se reconnaît à ses deux étages d'optiques avant,
# le haut sur la marche au pied du pare-brise.
DECOR = {
    "Pare-brise": ((strip(WINDSCREEN, 0.006), 1.84, "x", (0, 0.05)), "DECOR-GLASS", [(0, 0, 0)]),
    "Vitre avant": (([(1.11, 1.05), (0.38, 1.62), (0.03, 1.66), (0.03, 1.03)], 0.005, "x"),
                    "DECOR-GLASS", sides(0.910)),
    "Vitre arrière": (([(-0.03, 1.03), (-0.03, 1.662), (-0.60, 1.67), (-1.37, 1.666), (-1.37, 1.03)], 0.005, "x"),
                      "DECOR-GLASS", sides(0.910)),
    "Optique basse": ((ellipse(0.17, 0.065), 0.04, "z"), "DECOR-LIGHT", sides(0.69, 0.70, 1.975)),
    "Optique haute": ((ellipse(0.11, 0.04), 0.03, "z"), "DECOR-LIGHT", sides(0.60, 1.02, 1.275)),
    "Feu arrière": ((ellipse(0.07, 0.17), 0.02, "z"), "DECOR-TAIL-LIGHT", sides(0.81, 0.81, -2.0)),
    "Rétroviseur": ((ellipse(0.06, 0.05), 0.10, "z"), "DECOR-TRIM", sides(0.90, 1.12, 1.02)),
    "Pneu": ((ellipse(0.31, 0.31), 0.20, "x"), "DECOR-TYRE", at_wheels(0.78)),
    "Jante": ((ellipse(0.19, 0.19), 0.21, "x"), "DECOR-RIM", at_wheels(0.78)),
}

# Couleur de base (RVBA linéaire) par matériau ; alpha < 1 → verre teinté, assez
# opaque pour cacher l'intérieur vide de la maquette.
COLOURS = {
    "MAT-STEEL-SHEET": [0.10, 0.36, 0.55, 1.0],
    "MAT-PP-GRANULE": [0.06, 0.06, 0.07, 1.0],
    "MAT-ABS-GRANULE": [0.10, 0.10, 0.11, 1.0],
    "MAT-ALU-SHEET": [0.72, 0.74, 0.77, 1.0],
    "MAT-EPDM-RUBBER": [0.02, 0.02, 0.02, 1.0],
    "MAT-GLASS-FLOAT": [0.04, 0.05, 0.06, 0.85],
    "MAT-COPPER-WIRE": [0.72, 0.45, 0.20, 1.0],
    "DECOR-GLASS": [0.04, 0.05, 0.06, 0.85],
    "DECOR-LIGHT": [0.95, 0.95, 0.85, 1.0],
    "DECOR-TAIL-LIGHT": [0.75, 0.05, 0.05, 1.0],
    "DECOR-TRIM": [0.06, 0.06, 0.07, 1.0],
    "DECOR-TYRE": [0.03, 0.03, 0.03, 1.0],
    "DECOR-RIM": [0.75, 0.75, 0.78, 1.0],
}
