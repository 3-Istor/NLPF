"""Les chiffres portés par une ligne de l'arbre, et le marquage des modifications.

Deux montants cohabitent sur une même ligne, et les confondre est l'erreur que
l'ADR-0008 évite dans les données puis que l'affichage peut réintroduire :

  - ce que pèse **cette occurrence**, enfants compris — utile, mais il ne se
    somme pas entre niveaux ;
  - la contribution **propre**, qui elle se somme au total.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from carcost.application.browse_bom import children_of_path
from carcost.application.browse_bom import root_node
from carcost.application.price_resolution import resolve_unit_prices
from carcost.application.run_calculation import run_calculation
from carcost.application.scenario import Scenario, ScenarioParameter
from carcost.application.tree_view import marks_of, path_quantity, with_costs
from carcost.domain.bom import Bom, Edge
from carcost.domain.prices import PriceSnapshot
from factories import manufactured, purchased
from fakes import FakeSourcingRepository

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def bom() -> Bom:
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


def a_scenario(*parameters) -> Scenario:
    return Scenario(
        id="scn", bom_version="bom-test", display_currency="EUR",
        labour_rate=Decimal("60.00"), parameters=parameters,
    )


@pytest.fixture
def calculation(bom):
    def build(scenario=None):
        scenario = scenario or a_scenario()
        snapshot = PriceSnapshot(
            id="snp-1", taken_at=NOW, currency="EUR", source="mock",
            prices={"S": Decimal("10.000000")},
        )
        sourcing = FakeSourcingRepository().load("bom-test")
        resolved = resolve_unit_prices(bom, sourcing, snapshot, scenario)
        return run_calculation(
            bom=bom, scenario=scenario, snapshot=snapshot, resolved=resolved,
            now=NOW, calculation_id="calc-1",
        )

    return build


class TestPathQuantity:
    def test_multiplies_the_quantities_along_the_path(self, bom):
        assert path_quantity(bom, "V/A/S") == Decimal("8")   # 2 × 4
        assert path_quantity(bom, "V/B/S") == Decimal("15")  # 3 × 5

    def test_the_root_is_one_vehicle(self, bom):
        assert path_quantity(bom, "V") == Decimal("1")


class TestCostedLines:
    def test_a_line_carries_what_this_occurrence_weighs(self, bom, calculation):
        """Sous A, il y a 8 vis à 10 € : 80 €. Sous B, 15 vis : 150 €.
        La même pièce, deux lignes, deux montants — et 23 vis en tout."""
        nodes = with_costs(
            bom, children_of_path(bom, "V/A").items, calculation(), a_scenario()
        )
        screw = nodes[0]

        assert screw.quantity_on_path == Decimal("8")
        assert screw.rolled_up_contribution == Decimal("80")

    def test_the_own_contribution_is_the_one_that_sums(self, bom, calculation):
        """Sur une vis, les deux coïncident : une feuille n'a rien en dessous."""
        nodes = with_costs(
            bom, children_of_path(bom, "V/A").items, calculation(), a_scenario()
        )

        assert nodes[0].own_contribution == nodes[0].rolled_up_contribution

    def test_on_an_assembly_the_two_differ(self, bom, calculation):
        """A coûte 30 € de main-d'œuvre par unité, plus 4 vis à 10 €.
        Monté deux fois : 60 € en propre, 140 € enfants compris."""
        nodes = with_costs(
            bom, children_of_path(bom, "V").items, calculation(), a_scenario()
        )
        assembly = next(node for node in nodes if node.node.part_ref == "A")

        assert assembly.own_contribution == Decimal("60")
        assert assembly.rolled_up_contribution == Decimal("140")

    def test_a_part_without_price_says_so_instead_of_showing_zero(self, bom):
        scenario = a_scenario()
        empty = PriceSnapshot(
            id="snp-vide", taken_at=NOW, currency="EUR", source="mock", prices={}
        )
        resolved = resolve_unit_prices(
            bom, FakeSourcingRepository().load("bom-test"), empty, scenario
        )
        result = run_calculation(
            bom=bom, scenario=scenario, snapshot=empty, resolved=resolved,
            now=NOW, calculation_id="calc-2",
        )

        nodes = with_costs(bom, children_of_path(bom, "V/A").items, result, scenario)

        assert nodes[0].price_status == "MISSING"
        assert nodes[0].own_contribution is None

    def test_the_share_is_what_this_occurrence_weighs_in_the_total(
        self, bom, calculation
    ):
        """Total : 60 + 60 + 45 + 230 = 395. A pèse 140, B 195, S sous B 150."""
        result = calculation()
        under_v = {
            node.node.part_ref: node
            for node in with_costs(
                bom, children_of_path(bom, "V").items, result, a_scenario()
            )
        }
        under_b = with_costs(
            bom, children_of_path(bom, "V/B").items, result, a_scenario()
        )
        root = with_costs(bom, (root_node(bom),), result, a_scenario())[0]

        assert under_v["A"].rolled_up_contribution == Decimal("140")
        assert under_v["A"].share_of_total_pct == Decimal("35.4")
        assert under_v["B"].rolled_up_contribution == Decimal("195")
        assert under_v["B"].share_of_total_pct == Decimal("49.4")
        assert under_b[0].rolled_up_contribution == Decimal("150")
        assert under_b[0].share_of_total_pct == Decimal("38.0")
        assert root.share_of_total_pct == Decimal("100.0")

    def test_shares_do_not_sum_between_levels(self, bom, calculation):
        """La main-d'oeuvre propre de V (60 euros, 15,2 %) n'est dans aucun
        enfant : les parts des enfants ne font pas 100."""
        nodes = with_costs(
            bom, children_of_path(bom, "V").items, calculation(), a_scenario()
        )

        assert sum(node.share_of_total_pct for node in nodes) != Decimal("100.0")

    def test_a_line_without_price_has_no_share(self, bom):
        scenario = a_scenario()
        empty = PriceSnapshot(
            id="snp-vide", taken_at=NOW, currency="EUR", source="mock", prices={}
        )
        resolved = resolve_unit_prices(
            bom, FakeSourcingRepository().load("bom-test"), empty, scenario
        )
        result = run_calculation(
            bom=bom, scenario=scenario, snapshot=empty, resolved=resolved,
            now=NOW, calculation_id="calc-2",
        )

        nodes = with_costs(bom, children_of_path(bom, "V/A").items, result, scenario)

        assert nodes[0].share_of_total_pct is None



class TestPriceStatusOnTheLine:
    """Un prix dégradé se voit sur la ligne concernée, pas seulement sur le total.

    Sans ce marquage, l'écran annonce « prix dégradés » et laisse l'utilisateur
    chercher lequel parmi trois cents.
    """

    def screw(self, bom, snapshot, scenario=None):
        scenario = scenario or a_scenario()
        resolved = resolve_unit_prices(
            bom, FakeSourcingRepository().load("bom-test"), snapshot, scenario
        )
        result = run_calculation(
            bom=bom, scenario=scenario, snapshot=snapshot, resolved=resolved,
            now=NOW, calculation_id="calc-3",
        )
        return with_costs(bom, children_of_path(bom, "V/A").items, result, scenario)[0]

    def snapshot(self, **refs):
        return PriceSnapshot(
            id="snp-2", taken_at=NOW, currency="EUR", source="mock",
            prices={"S": Decimal("10.000000")}, **refs,
        )

    def test_a_fresh_price_is_ok(self, bom):
        assert self.screw(bom, self.snapshot()).price_status == "OK"

    def test_a_price_carried_over_from_the_previous_snapshot_says_so(self, bom):
        line = self.screw(bom, self.snapshot(fallback_refs=frozenset({"S"})))

        assert line.price_status == "FALLBACK"
        # Le montant reste affiché : un repli est un prix, pas un trou.
        assert line.own_contribution == Decimal("80")

    def test_a_refused_value_is_told_apart_from_an_absent_one(self, bom):
        line = self.screw(
            bom,
            self.snapshot(
                fallback_refs=frozenset({"S"}), quarantined_refs=frozenset({"S"})
            ),
        )

        assert line.price_status == "QUARANTINED"

    def test_a_forced_price_does_not_inherit_the_snapshot_s_trouble(self, bom):
        """Le prix forcé remplace celui du snapshot : l'origine de ce dernier
        ne dit plus rien du montant affiché."""
        scenario = a_scenario(
            ScenarioParameter(
                part_ref="S", scope="part", price_override=Decimal("9.50"),
                price_override_justification="devis ferme du 2026-09-20",
            )
        )
        line = self.screw(
            bom, self.snapshot(fallback_refs=frozenset({"S"})), scenario
        )

        assert line.price_status == "OK"


class TestModificationMarks:
    def test_a_touched_part_is_marked(self, bom):
        scenario = a_scenario(
            ScenarioParameter(part_ref="S", scope="part", supplier_id="SUP-DE")
        )

        marks = marks_of(bom, scenario)

        assert marks.is_modified("S") is True
        assert marks.is_modified("A") is False

    def test_every_ancestor_up_to_the_root_is_marked_too(self, bom):
        """Sans cette remontée, on ne retrouve plus ce qu'on a changé dans une
        nomenclature de quatre cents pièces."""
        scenario = a_scenario(
            ScenarioParameter(part_ref="S", scope="part", supplier_id="SUP-DE")
        )

        marks = marks_of(bom, scenario)

        assert marks.has_modified_descendant("V") is True
        assert marks.has_modified_descendant("A") is True
        assert marks.has_modified_descendant("B") is True

    def test_a_leaf_is_not_its_own_descendant(self, bom):
        scenario = a_scenario(
            ScenarioParameter(part_ref="S", scope="part", supplier_id="SUP-DE")
        )

        assert marks_of(bom, scenario).has_modified_descendant("S") is False

    def test_an_untouched_scenario_marks_nothing(self, bom):
        marks = marks_of(bom, a_scenario())

        assert marks.is_modified("S") is False
        assert marks.has_modified_descendant("V") is False
