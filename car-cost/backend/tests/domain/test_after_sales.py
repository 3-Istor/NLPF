"""Le SAV : des pièces de rechange livrées avec le véhicule, comptées sur demande.

La quantité SAV est portée par l'arête, à côté de la quantité montée. Le moteur
ne la connaît pas : on lui passe la nomenclature dont les arêtes comptent
montée + SAV. Il n'y a donc qu'une façon de cumuler les quantités.
"""

from __future__ import annotations

from decimal import Decimal

from carcost.domain.bom import Bom, Edge
from carcost.domain.engine import compute
from carcost.domain.scenario import CalculationInput
from factories import manufactured, purchased


def _bom() -> Bom:
    """V ×2→ A ×4(+1 SAV)→ S ; V ×3→ B ×5→ S.

    Le SAV est sur une seule des deux arêtes vers S : une implémentation qui
    l'ajouterait au total de la pièce plutôt qu'à l'arête le compterait une
    fois au lieu de deux (A est monté deux fois).
    """
    return Bom(
        root_ref="V",
        parts={
            "V": manufactured("V"),
            "A": manufactured("A"),
            "B": manufactured("B"),
            "S": purchased("S"),
        },
        edges=(
            Edge("V", "A", Decimal("2")),
            Edge("V", "B", Decimal("3")),
            Edge("A", "S", Decimal("4"), after_sales_quantity=Decimal("1")),
            Edge("B", "S", Decimal("5")),
        ),
    )


def _cumulative(bom: Bom, ref: str) -> Decimal:
    inputs = CalculationInput(
        bom=bom,
        unit_prices={"S": Decimal("10")},
        labour_rate=Decimal(0),
        transport_co2_per_kg={"S": Decimal(0)},
    )
    return compute(inputs).line(ref).cumulative_quantity


def test_after_sales_is_ignored_by_default():
    assert _cumulative(_bom(), "S") == Decimal("23")


def test_after_sales_adds_on_the_edge_it_belongs_to():
    """2×(4+1) + 3×5 = 25, et non 23 + 1 = 24."""
    assert _cumulative(_bom().with_after_sales(), "S") == Decimal("25")


def test_with_after_sales_leaves_the_version_untouched():
    """La version validée est partagée entre scénarios (ADR-0013) : activer le
    SAV sur l'un ne doit pas la modifier pour les autres."""
    bom = _bom()
    bom.with_after_sales()
    assert _cumulative(bom, "S") == Decimal("23")


def test_has_after_sales_says_whether_the_switch_changes_anything():
    assert _bom().has_after_sales
    plain = Bom(
        root_ref="V",
        parts={"V": manufactured("V"), "S": purchased("S")},
        edges=(Edge("V", "S", Decimal("2")),),
    )
    assert not plain.has_after_sales
