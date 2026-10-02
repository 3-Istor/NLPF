"""Le snapshot de calcul : nom obligatoire, clé d'unicité, copie défensive."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from carcost.domain.calculation_snapshot import (
    CalculationSnapshot,
    FrozenParameter,
    InvalidSnapshotName,
    name_key,
    snapshot_name,
)


def build(name: str = "Référence T3", parameters=None, active_rules=None):
    return CalculationSnapshot(
        id="snap-1",
        name=name,
        bom_version="v1",
        scenario_id="sc-1",
        scenario_name="Base",
        calculation_id="calc-1",
        price_snapshot_id="ps-1",
        display_currency="EUR",
        labour_rate=Decimal("42.5"),
        active_rules=active_rules if active_rules is not None else {"labour"},
        parameters=parameters if parameters is not None else [],
        created_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc),
    )


def test_the_name_is_trimmed():
    assert snapshot_name("  Référence T3 ") == "Référence T3"


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
def test_a_blank_name_is_refused(raw):
    with pytest.raises(InvalidSnapshotName):
        snapshot_name(raw)


def test_names_that_differ_only_by_case_or_accents_share_a_key():
    assert (
        name_key("Référence T3")
        == name_key("reference t3")
        == name_key("RÉFÉRENCE T3")
    )


def test_different_names_have_different_keys():
    assert name_key("Référence T3") != name_key("Référence T4")


def test_the_snapshot_does_not_share_the_caller_s_collections():
    parameters = [
        FrozenParameter(part_ref="P-2", labour_minutes=Decimal("3")),
        FrozenParameter(part_ref="P-1", price_override=Decimal("9")),
    ]
    rules = {"labour"}
    snapshot = build(parameters=parameters, active_rules=rules)
    before = snapshot.parameters

    parameters.append(FrozenParameter(part_ref="P-3"))
    rules.add("other")

    assert isinstance(snapshot.parameters, tuple)
    assert snapshot.parameters == before
    assert len(snapshot.parameters) == 2
    assert snapshot.active_rules == frozenset({"labour"})


def test_a_snapshot_cannot_be_built_without_a_name():
    with pytest.raises(InvalidSnapshotName):
        build(name="  ")
