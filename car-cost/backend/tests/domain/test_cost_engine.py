"""Le moteur de coût sur le DAG.

Chaque test ici peut échouer pour une vraie raison : il existe une
implémentation plausible, simple et fausse qui le fait tomber.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from carcost.domain.engine import compute
from carcost.domain.scenario import CalculationInput


def inputs(bom, *, prices=None, labour_rate="60") -> CalculationInput:
    return CalculationInput(
        bom=bom,
        unit_prices={"S": Decimal("10")} if prices is None else prices,
        labour_rate=Decimal(labour_rate),
        active_rules=frozenset({"labour"}),
    )


class TestCumulativeQuantities:
    def test_sums_over_all_paths(self, diamond):
        """2×4 + 3×5 = 23.

        Une implémentation qui traite le DAG comme un arbre renvoie 4 ou 5 ;
        une qui oublie la quantité du parent renvoie 9.
        """
        result = compute(inputs(diamond))

        assert result.line("S").cumulative_quantity == Decimal("23")

    def test_counts_occurrences_not_parents(self, diamond):
        result = compute(inputs(diamond))

        assert result.line("S").occurrence_count == 2
        assert result.line("A").cumulative_quantity == Decimal("2")

    def test_root_is_one_vehicle(self, diamond):
        result = compute(inputs(diamond))

        assert result.line("V").cumulative_quantity == Decimal("1")


class TestSingleEvaluation:
    def test_shared_part_is_evaluated_once(self, diamond):
        """Ce qui distingue une programmation dynamique d'une récursion naïve.

        Sur le losange la différence est d'une évaluation ; sur la Multipla,
        elle est de plusieurs ordres de grandeur.
        """
        lookups: list[str] = []

        class CountingPrices(dict):
            def __getitem__(self, ref):
                lookups.append(ref)
                return super().__getitem__(ref)

        compute(inputs(diamond, prices=CountingPrices({"S": Decimal("10")})))

        assert lookups.count("S") == 1


class TestConservation:
    def test_sum_of_own_contributions_equals_total(self, diamond):
        result = compute(inputs(diamond))

        assert sum(
            (line.own_contribution for line in result.lines), Decimal(0)
        ) == result.total_cost

    def test_root_full_unit_cost_equals_total(self, diamond):
        """Deux façons de dire la même chose : si elles divergent, l'une ment."""
        result = compute(inputs(diamond))

        assert result.line("V").full_unit_cost == result.total_cost

    def test_total_is_the_hand_computed_value(self, diamond):
        """23 vis à 10 € = 230 €, plus la main-d'œuvre :
        V une fois 60 min, A deux fois 30 min, B trois fois 15 min
        = 60 + 60 + 45 = 165 min à 60 €/h = 165 €. Total 395 €.
        """
        result = compute(inputs(diamond))

        assert result.total_cost == Decimal("395")


class TestLabourTimeFromTheScenario:
    def test_it_replaces_the_bom_time_on_every_unit(self, diamond):
        """A passe de 30 à 90 min, et il y a deux A : 2 × 60 min de plus à
        60 €/h, soit 120 €. 395 + 120 = 515."""
        result = compute(
            CalculationInput(
                bom=diamond,
                unit_prices={"S": Decimal("10")},
                labour_rate=Decimal("60"),
                labour_minutes_by_part={"A": Decimal("90")},
            )
        )

        assert result.total_cost == Decimal("515")

    def test_without_the_labour_rule_it_costs_nothing_either(self, diamond):
        """Désactiver la règle coupe toute la main-d'œuvre, celle du scénario
        comprise : 23 vis à 10 €."""
        result = compute(
            CalculationInput(
                bom=diamond,
                unit_prices={"S": Decimal("10")},
                labour_rate=Decimal("60"),
                active_rules=frozenset(),
                labour_minutes_by_part={"A": Decimal("90")},
            )
        )

        assert result.total_cost == Decimal("230")


class TestPrecision:
    def test_amounts_carry_no_more_precision_than_the_data(self, diamond):
        """Une division par soixante produit vingt-huit chiffres ; la donnée
        n'en porte pas autant. Sans cet arrondi à la source, un total sort avec
        vingt-cinq décimales de bruit."""
        result = compute(inputs(diamond))

        assert -result.line("A").own_unit_cost.as_tuple().exponent <= 6
        assert -result.total_cost.as_tuple().exponent <= 6


class TestValuationMode:
    def test_purchased_node_never_sums_children(self, diamond):
        result = compute(inputs(diamond))

        assert result.line("S").full_unit_cost == Decimal("10")

    def test_manufactured_node_never_reads_a_price(self, diamond):
        """Un prix qui traînerait sur un ensemble doit rester sans effet."""
        with_stray_price = compute(
            inputs(diamond, prices={"S": Decimal("10"), "A": Decimal("999")})
        )

        assert with_stray_price.total_cost == Decimal("395")

    def test_missing_price_on_a_purchased_part_is_reported_not_zeroed(self, diamond):
        result = compute(inputs(diamond, prices={}))

        assert result.is_incomplete
        assert "S" in result.parts_without_price
        assert result.line("S").own_contribution is None

    def test_an_incomplete_root_has_no_full_unit_cost(self, diamond):
        """Le total partiel n'est pas le coût du véhicule : la racine l'ignore."""
        result = compute(inputs(diamond, prices={}))

        assert result.line("V").full_unit_cost is None


class TestCarbon:
    """Empreinte carbone : de l'extraction à la sortie d'usine, transport
    fournisseur inclus, usage et fin de vie exclus (cadrage.md A10).

    `carbon_factor` porte le même sens sur une pièce achetée (matière) et un
    ensemble fabriqué (procédé d'assemblage) : jamais les enfants, sinon le
    CO2 serait compté deux fois — exactement comme `own_unit_cost`.
    """

    def test_a_purchased_part_s_co2_is_material_plus_transport(self, diamond):
        """S : facteur matière 2, 2 kg, transport 3 kg CO2e/kg → 2 + 2×3 = 8.

        La masse est délibérément différente de 1 : une implémentation qui
        oublierait de multiplier le transport par la masse donnerait le même
        résultat que la bonne sur une masse de 1, sans se faire remarquer.
        """
        result = compute(
            CalculationInput(
                bom=_with_part_overrides(diamond, carbon={"S": "2"}, mass={"S": "2"}),
                unit_prices={"S": Decimal("10")},
                labour_rate=Decimal("60"),
                transport_co2_per_kg={"S": Decimal("3")},
            )
        )

        assert result.line("S").own_unit_co2 == Decimal("8")
        # 23 vis (quantité cumulée du losange) × 8 kg CO2e.
        assert result.line("S").own_co2_contribution == Decimal("184")

    def test_a_manufactured_part_s_co2_is_only_its_own_factor(self, diamond):
        """A : facteur procédé 7, pas de transport ni de masse à connaître."""
        result = compute(
            CalculationInput(
                bom=_with_part_overrides(diamond, carbon={"A": "7"}),
                unit_prices={"S": Decimal("10")},
                labour_rate=Decimal("60"),
            )
        )

        assert result.line("A").own_unit_co2 == Decimal("7")
        # A est monté deux fois (quantité cumulée 2) sous V.
        assert result.line("A").own_co2_contribution == Decimal("14")

    def test_sum_of_co2_contributions_equals_total_co2(self, diamond):
        result = compute(
            CalculationInput(
                bom=_with_part_overrides(
                    diamond,
                    carbon={"S": "2", "A": "7", "B": "1", "V": "3"},
                    mass={"S": "2"},
                ),
                unit_prices={"S": Decimal("10")},
                labour_rate=Decimal("60"),
                transport_co2_per_kg={"S": Decimal("3")},
            )
        )

        assert sum(
            (line.own_co2_contribution for line in result.lines), Decimal(0)
        ) == result.total_co2

    def test_root_full_co2_equals_total_co2(self, diamond):
        """Deux façons de dire la même chose, comme pour le coût."""
        result = compute(
            CalculationInput(
                bom=_with_part_overrides(
                    diamond, carbon={"S": "2", "A": "7"}, mass={"S": "2"}
                ),
                unit_prices={"S": Decimal("10")},
                labour_rate=Decimal("60"),
                transport_co2_per_kg={"S": Decimal("3")},
            )
        )

        assert result.line("V").full_unit_co2 == result.total_co2

    def test_a_missing_price_leaves_its_own_co2_unknown_not_zero(self, diamond):
        """Même règle que pour un prix manquant : pas de zéro silencieux."""
        result = compute(
            CalculationInput(
                bom=_with_part_overrides(diamond, carbon={"S": "2"}),
                unit_prices={},
                labour_rate=Decimal("60"),
                transport_co2_per_kg={"S": Decimal("3")},
            )
        )

        assert result.line("S").own_co2_contribution is None
        # Les ensembles ne dépendent pas du prix de leurs enfants pour leur
        # propre facteur : leur contribution propre reste connue.
        assert result.line("A").own_co2_contribution is not None

    def test_without_any_carbon_factor_total_co2_is_zero_not_none(self, diamond):
        """Une pièce à facteur nul contribue zéro, ce qui n'est pas « inconnu »."""
        result = compute(inputs(diamond))

        assert result.total_co2 == Decimal(0)


def _with_part_overrides(bom, *, carbon: dict[str, str] | None = None, mass: dict[str, str] | None = None):
    from dataclasses import replace

    carbon = carbon or {}
    mass = mass or {}
    parts = {}
    for ref, part in bom.parts.items():
        changes = {}
        if ref in carbon:
            changes["carbon_factor"] = Decimal(carbon[ref])
        if ref in mass:
            changes["mass_kg"] = Decimal(mass[ref])
        parts[ref] = replace(part, **changes) if changes else part
    return replace(bom, parts=parts)


class TestPathScope:
    def test_a_missing_price_elsewhere_does_not_hide_a_path_override(self, diamond):
        """V/A n'a pas de prix (S manque sous A) ; V/B/S est surchargé.

        Une évaluation qui s'arrête au premier enfant sans prix ne visite jamais
        V/B : la surcharge disparaît alors de l'arbre dès que le calcul est
        incomplet, c'est-à-dire exactement quand on a besoin d'y voir clair.
        """
        result = compute(
            CalculationInput(
                bom=diamond,
                unit_prices={},
                labour_rate=Decimal("60"),
                unit_prices_by_path={"V/B/S": Decimal("7")},
            )
        )

        assert result.path_own_unit_costs["V/B/S"] == Decimal("7")
        # 15 min à 60 €/h, plus 5 vis à 7 €.
        assert result.path_full_unit_costs["V/B"] == Decimal("50")
        assert result.path_full_unit_costs["V"] is None


class TestGuards:
    def test_a_cycle_is_refused(self):
        from carcost.domain.bom import Bom, Edge
        from factories import manufactured

        cyclic = Bom(
            root_ref="X",
            parts={"X": manufactured("X"), "Y": manufactured("Y")},
            edges=(Edge("X", "Y", Decimal("1")), Edge("Y", "X", Decimal("1"))),
        )

        with pytest.raises(ValueError, match="cycle"):
            compute(inputs(cyclic, prices={}))
