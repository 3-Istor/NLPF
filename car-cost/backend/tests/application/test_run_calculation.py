"""Le calcul complet : total, décomposition, contributeurs, état, empreinte."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from carcost.application.price_resolution import resolve_unit_prices
from carcost.application.run_calculation import CalculationStatus, run_calculation
from carcost.application.scenario import (
    Plant,
    Scenario,
    ScenarioParameter,
    Sourcing,
    SupplierOffer,
)
from carcost.domain.bom import Bom, Edge
from carcost.domain.prices import PriceSnapshot
from factories import manufactured, purchased

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def bom() -> Bom:
    """Deux systèmes : un moteur et un châssis, une vis partagée entre eux."""
    parts = {
        "V": manufactured("V", labour="60"),
        "GMP": manufactured("GMP", labour="30"),
        "CHS": manufactured("CHS", labour="15"),
        "S": purchased("S"),
    }
    parts["GMP"] = _in_system(parts["GMP"], "GMP")
    parts["CHS"] = _in_system(parts["CHS"], "CHS")
    parts["S"] = _in_system(parts["S"], "FIX")
    return Bom(
        root_ref="V",
        parts=parts,
        edges=(
            Edge("V", "GMP", Decimal("2")),
            Edge("V", "CHS", Decimal("3")),
            Edge("GMP", "S", Decimal("4")),
            Edge("CHS", "S", Decimal("5")),
        ),
    )


def _in_system(part, system):
    from dataclasses import replace

    return replace(part, system=system)


@pytest.fixture
def sourcing() -> Sourcing:
    return Sourcing(
        offers={"S": (SupplierOffer("SUP", Decimal("1.000000"), is_default=True),)},
        plants={
            "SUP": (
                Plant("PLT", "SUP", "IT", Decimal("1.000000"), Decimal("0.02"),
                      is_default=True),
            )
        },
    )


@pytest.fixture
def snapshot() -> PriceSnapshot:
    return PriceSnapshot(
        id="snp-1", taken_at=NOW, currency="EUR", source="mock",
        prices={"S": Decimal("10.000000")},
    )


def a_scenario(*parameters) -> Scenario:
    return Scenario(
        id="scn", bom_version="bom-test", display_currency="EUR",
        labour_rate=Decimal("60.00"), active_rules=frozenset({"labour"}),
        parameters=parameters,
    )


def run(bom, sourcing, snapshot, scenario=None, **overrides):
    scenario = scenario or a_scenario()
    resolved = resolve_unit_prices(bom, sourcing, snapshot, scenario)
    return run_calculation(
        bom=bom,
        scenario=scenario,
        snapshot=snapshot,
        resolved=resolved,
        now=overrides.get("now", NOW),
        calculation_id=overrides.get("calculation_id", "calc-1"),
        snapshot_is_fallback=overrides.get("snapshot_is_fallback", False),
    )


class TestTotals:
    def test_the_total_is_the_hand_computed_value(self, bom, sourcing, snapshot):
        """23 vis à 10 € = 230 €, plus 165 min à 60 €/h = 165 €. Total 395 €."""
        assert run(bom, sourcing, snapshot).total_cost == Decimal("395")

    def test_the_sum_of_contributions_equals_the_total(self, bom, sourcing, snapshot):
        calculation = run(bom, sourcing, snapshot)

        assert sum(
            (line.own_contribution for line in calculation.lines), Decimal(0)
        ) == calculation.total_cost


class TestSystemBreakdown:
    def test_the_systems_sum_exactly_to_the_total(self, bom, sourcing, snapshot):
        """Critère d'acceptation de l'écran : la décomposition somme au total."""
        calculation = run(bom, sourcing, snapshot)

        assert sum(
            (system.cost for system in calculation.systems), Decimal(0)
        ) == calculation.total_cost

    def test_every_system_of_the_graph_appears_once(self, bom, sourcing, snapshot):
        calculation = run(bom, sourcing, snapshot)

        assert {system.system for system in calculation.systems} == {
            "TST", "GMP", "CHS", "FIX"
        }

    def test_shares_are_percentages_of_the_total(self, bom, sourcing, snapshot):
        calculation = run(bom, sourcing, snapshot)
        screws = next(s for s in calculation.systems if s.system == "FIX")

        assert screws.cost == Decimal("230")
        assert screws.share_pct == Decimal("58.2")  # 230 / 395


class TestContributors:
    def test_they_come_sorted_by_weight(self, bom, sourcing, snapshot):
        calculation = run(bom, sourcing, snapshot)

        contributions = [c.own_contribution for c in calculation.top_contributors]
        assert contributions == sorted(contributions, reverse=True)

    def test_each_one_carries_a_path_to_unfold_to(self, bom, sourcing, snapshot):
        calculation = run(bom, sourcing, snapshot)
        screw = next(c for c in calculation.top_contributors if c.part_ref == "S")

        assert screw.first_path in {"V/GMP/S", "V/CHS/S"}


class TestReproducibility:
    def test_two_identical_runs_give_the_same_total_to_the_cent(
        self, bom, sourcing, snapshot
    ):
        first = run(bom, sourcing, snapshot)
        second = run(bom, sourcing, snapshot, calculation_id="calc-2")

        assert first.total_cost == second.total_cost
        assert first.input_digest == second.input_digest

    def test_changing_a_parameter_changes_the_digest(self, bom, sourcing, snapshot):
        untouched = run(bom, sourcing, snapshot)
        forced = run(
            bom, sourcing, snapshot,
            scenario=a_scenario(
                ScenarioParameter(
                    part_ref="S", scope="part",
                    price_override=Decimal("9.000000"),
                    price_override_justification="devis",
                )
            ),
        )

        assert forced.input_digest != untouched.input_digest

    def test_the_digest_ignores_the_calculation_identifier_and_the_clock(
        self, bom, sourcing, snapshot
    ):
        """Sinon deux calculs identiques paraîtraient différents, et l'écran
        marquerait les totaux obsolètes sans raison."""
        first = run(bom, sourcing, snapshot)
        later = run(
            bom, sourcing, snapshot, calculation_id="calc-9",
            now=NOW + timedelta(hours=5),
        )

        assert first.input_digest == later.input_digest


class TestStatus:
    def test_everything_in_order_is_ok(self, bom, sourcing, snapshot):
        assert run(bom, sourcing, snapshot).status is CalculationStatus.OK

    def test_a_missing_price_makes_it_incomplete(self, bom, sourcing):
        empty = PriceSnapshot(
            id="snp-vide", taken_at=NOW, currency="EUR", source="mock", prices={}
        )

        calculation = run(bom, sourcing, empty)

        assert calculation.status is CalculationStatus.INCOMPLETE
        assert calculation.parts_without_price == ("S",)

    def test_a_fallback_snapshot_makes_it_degraded(self, bom, sourcing, snapshot):
        calculation = run(bom, sourcing, snapshot, snapshot_is_fallback=True)

        assert calculation.status is CalculationStatus.DEGRADED

    def test_a_stale_snapshot_makes_it_degraded_but_still_produces_a_total(
        self, bom, sourcing
    ):
        old = PriceSnapshot(
            id="snp-vieux", taken_at=NOW - timedelta(days=3), currency="EUR",
            source="mock", prices={"S": Decimal("10.000000")},
        )

        calculation = run(bom, sourcing, old)

        assert calculation.status is CalculationStatus.DEGRADED
        assert calculation.total_cost == Decimal("395")

    def test_the_age_of_the_prices_travels_with_the_result(self, bom, sourcing):
        old = PriceSnapshot(
            id="snp-vieux", taken_at=NOW - timedelta(hours=30), currency="EUR",
            source="mock", prices={"S": Decimal("10.000000")},
        )

        calculation = run(bom, sourcing, old)

        assert calculation.snapshot_age == timedelta(hours=30)
        assert calculation.snapshot_id == "snp-vieux"
