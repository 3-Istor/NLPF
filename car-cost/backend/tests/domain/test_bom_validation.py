"""Le contrôle d'intégrité de la nomenclature.

Chaque fixture casse **une** règle, sur un graphe par ailleurs valide : si le
contrôle en signale une autre, ou aucune, c'est lui qui est faux. Le losange,
lui, doit passer sans rien signaler — un contrôle trop zélé qui refuserait une
pièce partagée traiterait le graphe comme un arbre.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from carcost.domain.bom import Bom, Edge
from carcost.domain.bom_validation import validate_bom
from factories import manufactured, purchased


def codes(bom: Bom) -> list[str]:
    return [violation.code for violation in validate_bom(bom)]


def with_edges(bom: Bom, *edges: Edge) -> Bom:
    return Bom(root_ref=bom.root_ref, parts=bom.parts, edges=bom.edges + edges)


def with_part(bom: Bom, part) -> Bom:
    return Bom(
        root_ref=bom.root_ref, parts={**bom.parts, part.ref: part}, edges=bom.edges
    )


def test_the_diamond_is_valid(diamond):
    assert validate_bom(diamond) == ()


def test_a_cycle_is_reported(diamond):
    bom = with_edges(diamond, Edge("B", "V", Decimal("1")))

    assert "CYCLE" in codes(bom)


def test_a_self_loop_is_reported_as_a_cycle(diamond):
    bom = with_edges(diamond, Edge("A", "A", Decimal("1")))

    assert "CYCLE" in codes(bom)


def test_an_orphan_is_reported_with_its_reference(diamond):
    bom = with_part(diamond, purchased("LOST"))

    violations = validate_bom(bom)

    assert [(v.code, v.part_ref) for v in violations] == [("ORPHAN", "LOST")]


def test_a_second_root_is_an_orphan(diamond):
    """Deux sommets sans parent : l'un est la racine déclarée, l'autre est
    employé nulle part. Sa pièce serait ignorée du total sans que rien ne le
    dise."""
    other_root = manufactured("W", labour="1")
    bom = Bom(
        root_ref="V",
        parts={**diamond.parts, "W": other_root},
        edges=diamond.edges + (Edge("W", "S", Decimal("1")),),
    )

    assert codes(bom) == ["ORPHAN"]


def test_a_root_with_a_parent_is_reported(diamond):
    """V sous A n'est pas forcément un cycle si A n'est plus sous V : ici, on
    ajoute un vrai sommet T au-dessus de V, et V cesse d'être la racine."""
    top = manufactured("T", labour="1")
    bom = Bom(
        root_ref="V",
        parts={**diamond.parts, "T": top},
        edges=diamond.edges + (Edge("T", "V", Decimal("1")),),
    )

    assert "ROOT_HAS_PARENT" in codes(bom)


def test_a_duplicated_edge_is_reported(diamond):
    """La même paire deux fois : la quantité cumulée de S passerait de 23 à 31,
    un chiffre plausible."""
    bom = with_edges(diamond, Edge("A", "S", Decimal("4")))

    assert codes(bom) == ["DUPLICATE_EDGE"]


@pytest.mark.parametrize("quantity", ["0", "-1"])
def test_a_non_positive_quantity_is_reported(diamond, quantity):
    edges = tuple(
        replace(edge, quantity=Decimal(quantity)) if edge.child_ref == "B" else edge
        for edge in diamond.edges
    )
    bom = Bom(root_ref="V", parts=diamond.parts, edges=edges)

    assert codes(bom) == ["NON_POSITIVE_QUANTITY"]


def test_a_purchased_part_with_children_is_reported(diamond):
    """Son prix couvre déjà son contenu : compter les enfants en plus, c'est
    compter deux fois (ADR-0008)."""
    bom = with_edges(
        with_part(diamond, purchased("NUT")), Edge("S", "NUT", Decimal("1"))
    )

    assert codes(bom) == ["PURCHASED_WITH_CHILDREN"]


def test_a_manufactured_part_without_children_is_reported(diamond):
    bom = with_edges(
        with_part(diamond, manufactured("EMPTY", labour="1")),
        Edge("A", "EMPTY", Decimal("1")),
    )

    assert codes(bom) == ["MANUFACTURED_WITHOUT_CHILDREN"]


def test_a_manufactured_part_without_labour_is_reported(diamond):
    parts = {**diamond.parts, "A": replace(diamond.parts["A"], labour_minutes=None)}
    bom = Bom(root_ref="V", parts=parts, edges=diamond.edges)

    assert codes(bom) == ["MANUFACTURED_WITHOUT_LABOUR"]


def test_a_purchased_part_with_labour_is_reported(diamond):
    parts = {**diamond.parts, "S": replace(diamond.parts["S"], labour_minutes=Decimal("3"))}
    bom = Bom(root_ref="V", parts=parts, edges=diamond.edges)

    assert codes(bom) == ["PURCHASED_WITH_LABOUR"]


def test_a_negative_carbon_factor_is_reported(diamond):
    parts = {**diamond.parts, "S": purchased("S", carbon="-0.1")}
    bom = Bom(root_ref="V", parts=parts, edges=diamond.edges)

    assert codes(bom) == ["NEGATIVE_CARBON_FACTOR"]


def test_every_violation_is_reported_not_only_the_first(diamond):
    """Un import refusé doit dire tout ce qui ne va pas : corriger une erreur
    pour découvrir la suivante au prochain essai coûte un aller-retour par
    erreur."""
    bom = with_edges(
        with_part(diamond, purchased("LOST")), Edge("A", "S", Decimal("4"))
    )

    assert sorted(codes(bom)) == ["DUPLICATE_EDGE", "ORPHAN"]


class TestConstruction:
    """Ce qui ne peut même pas former un graphe est refusé à la construction,
    avec un message qui nomme la référence — pas un KeyError."""

    def test_an_edge_to_an_unknown_part_is_refused(self, diamond):
        with pytest.raises(ValueError, match="GHOST"):
            with_edges(diamond, Edge("A", "GHOST", Decimal("1")))

    def test_an_edge_from_an_unknown_part_is_refused(self, diamond):
        with pytest.raises(ValueError, match="GHOST"):
            with_edges(diamond, Edge("GHOST", "S", Decimal("1")))

    def test_an_unknown_root_is_refused(self, diamond):
        with pytest.raises(ValueError, match="NOWHERE"):
            Bom(root_ref="NOWHERE", parts=diamond.parts, edges=diamond.edges)


def test_a_reference_containing_the_path_separator_is_reported(diamond):
    bom = with_edges(
        with_part(diamond, purchased("S/X")), Edge("A", "S/X", Decimal("1"))
    )
    assert [(v.code, v.part_ref) for v in validate_bom(bom)] == [
        ("PATH_SEPARATOR_IN_REF", "S/X")
    ]
