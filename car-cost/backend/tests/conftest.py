"""Fixtures de domaine. Aucune base, aucun réseau, aucun fichier."""

from __future__ import annotations

from decimal import Decimal

import pytest

from carcost.domain.bom import Bom, Edge
from factories import manufactured, purchased


@pytest.fixture
def diamond() -> Bom:
    """Le losange : une pièce partagée entre deux parents.

            V
        ×2 /  \\ ×3
          A    B
        ×4 \\  / ×5
             S

    Aucune quantité ne vaut 1 : une implémentation qui oublie de multiplier par
    la quantité du parent, ou qui traite le graphe comme un arbre, donne un
    résultat visiblement faux au lieu d'un résultat plausible.

    Quantité cumulée de S pour un V : 2×4 + 3×5 = 23.
    """
    return Bom(
        root_ref="V",
        parts={
            "V": manufactured("V", labour="60"),
            "A": manufactured("A", labour="30"),
            "B": manufactured("B", labour="15"),
            "S": purchased("S"),
        },
        edges=(
            Edge("V", "A", Decimal("2")),
            Edge("V", "B", Decimal("3")),
            Edge("A", "S", Decimal("4")),
            Edge("B", "S", Decimal("5")),
        ),
    )
