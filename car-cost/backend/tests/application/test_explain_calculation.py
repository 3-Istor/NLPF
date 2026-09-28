"""D'où vient un montant, et quelles lignes n'ont pas un prix sain.

Les valeurs sont calculées à la main sur le losange :

  S : référence 12,5 × fournisseur 1,2 × usine 0,9 = 13,5 par vis
  A : 4 vis × 13,5 + 30 min à 60 €/h = 54 + 30 = 84
  V/A/S : 2 × 4 = 8 vis par ce chemin ; 2×4 + 3×5 = 23 dans le véhicule
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from carcost.application.browse_bom import PathNotFound
from carcost.application.calculation_issues import calculation_issues
from carcost.application.explain_calculation import (
    AssemblyBreakdown,
    CatalogueBreakdown,
    OverrideBreakdown,
    explain_line,
)
from carcost.application.price_resolution import PriceExplanation, resolve_unit_prices
from carcost.application.run_calculation import run_calculation
from carcost.application.scenario import (
    Plant,
    Scenario,
    ScenarioParameter,
    Sourcing,
    SupplierOffer,
)
from carcost.domain.bom import Bom, Edge
from carcost.domain.prices import PriceSnapshot
from factories import purchased

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def bom(diamond) -> Bom:
    """Le losange, plus un écrou N sous B que le snapshot ne connaît pas."""
    return Bom(
        root_ref="V",
        parts={**diamond.parts, "N": purchased("N")},
        edges=diamond.edges + (Edge("B", "N", Decimal("2")),),
    )


def sourcing(multiplier: str = "1.200000") -> Sourcing:
    offers = (
        SupplierOffer("SUP-IT", Decimal("1.000000"), is_default=True, name="Bulloni"),
        SupplierOffer("SUP-DE", Decimal(multiplier), is_default=False, name="Schrauben"),
    )
    return Sourcing(
        offers={"S": offers, "N": offers},
        plants={
            "SUP-IT": (
                Plant("PLT-IT", "SUP-IT", "IT", Decimal("1.000000"),
                      Decimal("0.02"), is_default=True),
            ),
            "SUP-DE": (
                Plant("PLT-DE", "SUP-DE", "DE", Decimal("1.000000"),
                      Decimal("0.04"), is_default=True),
                Plant("PLT-PL", "SUP-DE", "PL", Decimal("0.900000"),
                      Decimal("0.06"), is_default=False),
            ),
        },
    )


def snapshot(**overrides) -> PriceSnapshot:
    return PriceSnapshot(
        id="snp-1", taken_at=NOW, currency="EUR", source="mock",
        prices={"S": Decimal("12.500000")},
        missing_refs=frozenset({"N"}),
        **overrides,
    )


def scenario(*parameters) -> Scenario:
    return Scenario(
        id="scn", bom_version="bom-test", display_currency="EUR",
        labour_rate=Decimal("60.00"), active_rules=frozenset({"labour"}),
        parameters=parameters,
    )


ON_THE_POLISH_PLANT = ScenarioParameter(
    part_ref="S", scope="part", supplier_id="SUP-DE", plant_id="PLT-PL"
)


def calculate(bom, the_scenario, the_snapshot, the_sourcing=None):
    the_sourcing = the_sourcing or sourcing()
    resolved = resolve_unit_prices(bom, the_sourcing, the_snapshot, the_scenario)
    return run_calculation(
        bom=bom, scenario=the_scenario, snapshot=the_snapshot, resolved=resolved,
        now=NOW, calculation_id="calc-1",
    )


def as_read_back(calculation):
    """Ce que le dépôt Postgres rend : fournisseur et usine, pas les facteurs."""
    return replace(
        calculation,
        explanations={
            ref: PriceExplanation(
                part_ref=ref, unit_price=explanation.unit_price,
                supplier_id=explanation.supplier_id, plant_id=explanation.plant_id,
            )
            for ref, explanation in calculation.explanations.items()
            if explanation.supplier_id is not None
        },
    )


def explain(bom, calculation, path, *, the_scenario=None, the_sourcing=None,
            the_snapshot=None):
    return explain_line(
        calculation=calculation,
        bom=bom,
        scenario=the_scenario or scenario(ON_THE_POLISH_PLANT),
        snapshot=the_snapshot or snapshot(),
        sourcing=the_sourcing or sourcing(),
        path=path,
    )


class TestPurchasedPart:
    def test_the_unit_cost_is_split_into_its_three_factors(self, bom):
        calculation = calculate(bom, scenario(ON_THE_POLISH_PLANT), snapshot())

        breakdown = explain(bom, calculation, "V/A/S").breakdown

        assert isinstance(breakdown, CatalogueBreakdown)
        assert (
            breakdown.reference_price,
            breakdown.supplier_multiplier,
            breakdown.plant_coefficient,
            breakdown.unit_cost,
        ) == (Decimal("12.5"), Decimal("1.2"), Decimal("0.9"), Decimal("13.5"))
        assert breakdown.reproduced is True

    def test_the_factors_are_found_again_after_a_restart(self, bom):
        """Relu en base, un calcul ne garde que le fournisseur et l'usine ; le
        snapshot et le sourcing, figés, redonnent le reste."""
        calculation = as_read_back(
            calculate(bom, scenario(ON_THE_POLISH_PLANT), snapshot())
        )

        breakdown = explain(bom, calculation, "V/A/S").breakdown

        assert breakdown.reference_price == Decimal("12.5")
        assert breakdown.supplier_multiplier == Decimal("1.2")
        assert breakdown.reproduced is True

    def test_factors_that_no_longer_give_the_recorded_price_are_flagged(self, bom):
        """Un coefficient changé depuis ne doit pas passer pour l'explication
        du prix enregistré : la formule afficherait un autre résultat que la
        ligne."""
        calculation = as_read_back(
            calculate(bom, scenario(ON_THE_POLISH_PLANT), snapshot())
        )

        breakdown = explain(
            bom, calculation, "V/A/S", the_sourcing=sourcing(multiplier="1.300000")
        ).breakdown

        assert breakdown.reproduced is False
        assert breakdown.unit_cost == Decimal("13.5"), "le prix enregistré reste"

    def test_a_forced_price_shows_its_justification_not_factors(self, bom):
        forced = ScenarioParameter(
            part_ref="S", scope="part", price_override=Decimal("9.99"),
            price_override_justification="devis du 2026-09-20",
        )
        calculation = calculate(bom, scenario(forced), snapshot())

        breakdown = explain(
            bom, calculation, "V/A/S", the_scenario=scenario(forced)
        ).breakdown

        assert breakdown == OverrideBreakdown(
            unit_cost=Decimal("9.99"), justification="devis du 2026-09-20"
        )

    def test_a_missing_price_is_explained_as_missing_not_as_zero(self, bom):
        calculation = calculate(bom, scenario(), snapshot())

        explanation = explain(bom, calculation, "V/B/N", the_scenario=scenario())

        assert explanation.breakdown is None
        assert explanation.price_status == "MISSING"


class TestQuantities:
    def test_the_path_and_the_vehicle_quantities_are_both_given(self, bom):
        calculation = calculate(bom, scenario(ON_THE_POLISH_PLANT), snapshot())

        explanation = explain(bom, calculation, "V/A/S")

        assert (explanation.quantity_on_path, explanation.cumulative_quantity) == (
            Decimal("8"),
            Decimal("23"),
        )


class TestAssembly:
    def test_an_assembly_is_its_children_plus_its_labour_and_no_price(self, bom):
        calculation = calculate(bom, scenario(ON_THE_POLISH_PLANT), snapshot())

        breakdown = explain(bom, calculation, "V/A").breakdown

        assert isinstance(breakdown, AssemblyBreakdown)
        assert [(c.part_ref, c.quantity, c.contribution) for c in breakdown.children] == [
            ("S", Decimal("4"), Decimal("54"))
        ]
        assert (breakdown.labour_cost, breakdown.unit_cost) == (
            Decimal("30"),
            Decimal("84"),
        )

    def test_an_assembly_with_an_unpriced_child_has_no_unit_cost(self, bom):
        calculation = calculate(bom, scenario(), snapshot())

        breakdown = explain(bom, calculation, "V/B", the_scenario=scenario()).breakdown

        assert breakdown.children_cost is None
        assert breakdown.unit_cost is None


class TestAppliedParameter:
    def test_the_parameter_in_force_is_named(self, bom):
        calculation = calculate(bom, scenario(ON_THE_POLISH_PLANT), snapshot())

        explanation = explain(bom, calculation, "V/A/S")

        assert explanation.applied_parameter == ON_THE_POLISH_PLANT
        assert explanation.parameters_changed_since is False

    def test_after_a_change_the_current_parameter_is_not_passed_off_as_applied(
        self, bom
    ):
        """Le scénario porte maintenant un autre paramètre sur S : c'est
        précisément celui qu'il ne faut pas présenter comme appliqué."""
        calculation = calculate(bom, scenario(ON_THE_POLISH_PLANT), snapshot())
        since = ScenarioParameter(part_ref="S", scope="part", supplier_id="SUP-IT")

        explanation = explain(
            bom, calculation, "V/A/S", the_scenario=scenario(since)
        )

        assert explanation.applied_parameter is None
        assert explanation.parameters_changed_since is True


class TestPath:
    def test_a_path_that_does_not_start_at_the_root_is_refused(self, bom):
        calculation = calculate(bom, scenario(), snapshot())

        with pytest.raises(PathNotFound):
            explain(bom, calculation, "A/S", the_scenario=scenario())

    def test_a_path_through_a_missing_edge_is_refused(self, bom):
        calculation = calculate(bom, scenario(), snapshot())

        with pytest.raises(PathNotFound):
            explain(bom, calculation, "V/S", the_scenario=scenario())


class TestIssues:
    def test_each_unhealthy_line_is_listed_with_a_path_to_unfold(self, bom):
        degraded = snapshot(
            fallback_refs=frozenset({"S"}), quarantined_refs=frozenset({"S"})
        )
        calculation = calculate(bom, scenario(), degraded)

        issues = calculation_issues(calculation, bom)

        assert [(i.kind, i.part_ref, i.path) for i in issues] == [
            ("MISSING_PRICE", "N", "V/B/N"),
            ("QUARANTINED", "S", "V/A/S"),
        ]

    def test_a_healthy_calculation_has_no_issue(self, bom):
        healthy = replace(snapshot(), missing_refs=frozenset())
        priced = replace(healthy, prices={"S": Decimal("1"), "N": Decimal("1")})
        calculation = calculate(bom, scenario(), priced)

        assert calculation_issues(calculation, bom) == ()
