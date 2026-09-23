"""« Ce total est-il encore le bon ? »

C'est une question à laquelle seul le serveur peut répondre : le navigateur ne
connaît pas le graphe et ne sait pas ce qu'un paramètre a touché (ADR-0009).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from carcost.application.calculation_state import CalculationState, state_of
from carcost.application.run_calculation import input_digest
from carcost.application.scenario import Scenario, ScenarioParameter
from carcost.domain.prices import PriceSnapshot

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def a_scenario(*parameters) -> Scenario:
    return Scenario(
        id="scn", bom_version="bom-test", display_currency="EUR",
        labour_rate=Decimal("42.00"), parameters=parameters,
    )


def a_snapshot(identifier="snp-1") -> PriceSnapshot:
    return PriceSnapshot(
        id=identifier, taken_at=NOW, currency="EUR", source="mock",
        prices={"S": Decimal("10")},
    )


class TestStates:
    def test_a_scenario_never_calculated(self):
        state, reason = state_of(a_scenario(), a_snapshot(), last_digest=None)

        assert state is CalculationState.NEVER_RUN
        assert reason is None

    def test_nothing_changed_since_the_last_calculation(self):
        scenario, snapshot = a_scenario(), a_snapshot()

        state, _ = state_of(
            scenario, snapshot, last_digest=input_digest(scenario, snapshot)
        )

        assert state is CalculationState.UP_TO_DATE

    def test_a_changed_parameter_makes_the_totals_stale(self):
        before = a_scenario()
        digest = input_digest(before, a_snapshot())
        after = a_scenario(
            ScenarioParameter(part_ref="S", scope="part", supplier_id="SUP-DE")
        )

        state, reason = state_of(
            after, a_snapshot(), last_digest=digest, last_snapshot_id="snp-1"
        )

        assert state is CalculationState.PARAMETERS_CHANGED
        assert reason == "parameters"

    def test_a_newer_snapshot_also_makes_the_totals_stale(self):
        """Les paramètres n'ont pas bougé, mais les prix si. Afficher l'ancien
        total comme frais serait une faute, pas un détail."""
        scenario = a_scenario()
        digest = input_digest(scenario, a_snapshot("snp-1"))

        state, reason = state_of(
            scenario, a_snapshot("snp-2"),
            last_digest=digest, last_snapshot_id="snp-1",
        )

        assert state is CalculationState.PARAMETERS_CHANGED
        assert reason == "prices"

    def test_without_any_snapshot_nothing_can_be_calculated(self):
        state, _ = state_of(a_scenario(), None, last_digest=None)

        assert state is CalculationState.NO_PRICES


class TestScopeLabel:
    """Ce que l'écran doit afficher quand on pose un paramètre (ADR-0002)."""

    def test_a_part_scope_says_how_many_occurrences_it_touches(self):
        from carcost.application.calculation_state import scope_label

        assert scope_label("part", occurrences=12) == (
            "S'applique aux 12 occurrences de cette pièce"
        )

    def test_a_single_occurrence_is_not_written_in_the_plural(self):
        from carcost.application.calculation_state import scope_label

        assert scope_label("part", occurrences=1) == (
            "S'applique à l'unique occurrence de cette pièce"
        )

    def test_a_path_scope_says_it_touches_only_this_one(self):
        from carcost.application.calculation_state import scope_label

        assert scope_label("path", occurrences=12) == (
            "S'applique à cette occurrence uniquement"
        )

    def test_an_unknown_scope_is_refused_rather_than_described_vaguely(self):
        from carcost.application.calculation_state import scope_label

        with pytest.raises(ValueError):
            scope_label("partout", occurrences=3)
