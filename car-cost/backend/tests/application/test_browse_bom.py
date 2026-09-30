"""Parcourir le graphe : déplier un nœud, remonter les emplois, chercher.

Tout ce qui est calculé ici l'est côté serveur, parce que le navigateur ne
possède pas le graphe et ne peut donc rien en déduire (ADR-0009).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from carcost.application.browse_bom import (
    PathNotFound,
    children_of_path,
    root_node,
    search_parts,
    search_summary,
    SearchSummary,
    where_used,
)
from carcost.domain.bom import Bom, Edge
from factories import manufactured, purchased


@pytest.fixture
def diamond() -> Bom:
    """V ×2→ A ×4→ S, V ×3→ B ×5→ S. La vis est montée à deux endroits."""
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


class TestUnfolding:
    def test_the_root_is_a_path_of_one(self, diamond):
        node = root_node(diamond)

        assert node.path == "V"
        assert node.has_children is True

    def test_returns_direct_children_and_nothing_else(self, diamond):
        page = children_of_path(diamond, "V")

        assert [child.part_ref for child in page.items] == ["A", "B"]
        assert page.total == 2

    def test_each_child_carries_its_own_path(self, diamond):
        page = children_of_path(diamond, "V/A")

        assert page.items[0].path == "V/A/S"

    def test_carries_the_edge_quantity_not_the_cumulative_one(self, diamond):
        """Sur l'arête A→S il y a 4 vis ; dans le véhicule il y en a 23.
        La ligne de l'arbre montre 4 — c'est « × 4 » à cet endroit-là."""
        page = children_of_path(diamond, "V/A")

        assert page.items[0].edge_quantity == Decimal("4")

    def test_a_leaf_says_it_has_no_children(self, diamond):
        page = children_of_path(diamond, "V/A")

        assert page.items[0].has_children is False
        assert page.items[0].child_count == 0

    def test_paginates_without_losing_the_total(self, diamond):
        page = children_of_path(diamond, "V", limit=1, offset=1)

        assert [child.part_ref for child in page.items] == ["B"]
        assert page.total == 2


class TestSharedParts:
    def test_parents_and_occurrences_are_two_different_numbers(self, diamond):
        """Deux parents, deux occurrences ici — mais ils divergent dès qu'un
        sous-ensemble est lui-même monté plusieurs fois. Le badge affiche les
        occurrences."""
        page = children_of_path(diamond, "V/A")
        screw = page.items[0]

        assert screw.parent_count == 2
        assert screw.occurrence_count == 2

    def test_the_same_part_is_reached_by_two_different_paths(self, diamond):
        left = children_of_path(diamond, "V/A").items[0]
        right = children_of_path(diamond, "V/B").items[0]

        assert left.part_ref == right.part_ref
        assert left.path != right.path


class TestWhereUsed:
    def test_lists_every_path_that_reaches_the_part(self, diamond):
        page = where_used(diamond, "S")

        assert {occurrence.path for occurrence in page.items} == {"V/A/S", "V/B/S"}

    def test_each_occurrence_says_how_many_are_needed_there(self, diamond):
        page = where_used(diamond, "S")
        by_path = {o.path: o.quantity_on_path for o in page.items}

        assert by_path["V/A/S"] == Decimal("8")   # 2 × 4
        assert by_path["V/B/S"] == Decimal("15")  # 3 × 5

    def test_the_labels_of_the_path_are_given_so_it_reads(self, diamond):
        page = where_used(diamond, "S")

        assert page.items[0].path_labels[0] == "V"


class TestRefusals:
    def test_a_path_that_is_not_a_chain_of_edges_is_refused(self, diamond):
        """V et S existent, mais aucune arête ne va de l'un à l'autre."""
        with pytest.raises(PathNotFound):
            children_of_path(diamond, "V/S")

    def test_a_path_that_does_not_start_at_the_root_is_refused(self, diamond):
        with pytest.raises(PathNotFound):
            children_of_path(diamond, "A/S")

    def test_an_unknown_reference_is_refused(self, diamond):
        with pytest.raises(PathNotFound):
            children_of_path(diamond, "V/NOWHERE")


class TestSearch:
    def test_finds_by_reference_and_returns_the_paths_to_unfold(self, diamond):
        hits = search_parts(diamond, "S")

        assert hits[0].part_ref == "S"
        assert set(hits[0].paths) == {"V/A/S", "V/B/S"}

    def test_is_case_insensitive_and_matches_the_label(self, diamond):
        assert search_parts(diamond, "s")[0].part_ref == "S"

    def test_says_when_it_truncated_the_paths(self, diamond):
        hits = search_parts(diamond, "S", max_paths=1)

        assert len(hits[0].paths) == 1
        assert hits[0].paths_truncated is True


@pytest.fixture
def labelled() -> Bom:
    """Libellés accentués, différents des références (sinon le test ne peut pas échouer).

    SCREW est monté deux fois : sous HARNESS et sous RACK.
    """
    def named(part, label):
        return replace(part, label=label)

    return Bom(
        root_ref="VEH",
        parts={
            "VEH": named(manufactured("VEH", labour="1"), "Véhicule"),
            "HARNESS": named(manufactured("HARNESS", labour="1"), "Faisceau électrique"),
            "RACK": named(manufactured("RACK", labour="1"), "Crémaillère de direction"),
            "SCREW": named(purchased("SCREW"), "vis M6"),
        },
        edges=(
            Edge("VEH", "HARNESS", Decimal("1")),
            Edge("VEH", "RACK", Decimal("1")),
            Edge("HARNESS", "SCREW", Decimal("2")),
            Edge("RACK", "SCREW", Decimal("2")),
        ),
    )


class TestSearchFolding:
    @pytest.mark.parametrize("query", ["electrique", "électrique", "ÉLECTRIQUE"])
    def test_accents_and_case_do_not_matter(self, labelled, query):
        assert [h.part_ref for h in search_parts(labelled, query)] == ["HARNESS"]

    def test_cremaillere_finds_the_rack(self, labelled):
        assert [h.part_ref for h in search_parts(labelled, "cremaillere")] == ["RACK"]

    def test_upper_case_finds_lower_case(self, labelled):
        assert [h.part_ref for h in search_parts(labelled, "VIS")] == ["SCREW"]

    def test_the_summary_counts_beyond_the_limit(self, labelled):
        # « e » trouve les quatre pièces (VEH, HARNESS, RACK, et SCREW par sa
        # référence) : 1 + 1 + 1 + 2 emplacements = 5.
        hits = search_parts(labelled, "e", limit=2)
        summary = search_summary(labelled, "e")

        assert len(hits) == 2
        assert summary.total_parts == 4
        assert summary.total_occurrences == 5

    def test_the_summary_sums_the_mountings_of_a_shared_part(self, labelled):
        # SCREW est montée sous HARNESS et sous RACK : 2 emplacements.
        assert search_summary(labelled, "vis") == SearchSummary(1, 2)

    def test_an_empty_query_finds_nothing(self, labelled):
        assert search_parts(labelled, "   ") == []
        assert search_summary(labelled, "   ") == SearchSummary(0, 0)

    def test_the_default_keeps_up_to_50_paths(self, labelled):
        assert search_parts.__kwdefaults__["max_paths"] == 50
