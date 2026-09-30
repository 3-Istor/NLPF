"""NLPF-45 : recommandation contrainte, déterministe et sélectionnable."""

from dataclasses import replace
from decimal import Decimal

import pytest

from carcost.application.recommend_sourcing import (
    IncompleteBaseline,
    SourcingConstraints,
    apply_recommendations,
    recommend,
)
from carcost.application.run_calculation import CalculationStatus
from carcost.application.price_resolution import resolve_unit_prices
from carcost.application.run_calculation import run_calculation
from carcost.application.scenario import Scenario, ScenarioParameter, Sourcing
from carcost.domain.prices import PriceSnapshot
from fakes import FakeSourcingRepository
from .test_parameterized_calculation import NOW, calculate


def base_scenario():
    return Scenario(
        id="base", name="Base", bom_version="bom-test",
        display_currency="EUR", labour_rate=Decimal("60"),
    )


def recommendations(diamond, constraints=SourcingConstraints()):
    return report(diamond, constraints).recommendations


def report(diamond, constraints=SourcingConstraints()):
    return recommend(
        bom=diamond,
        sourcing=FakeSourcingRepository().sourcing,
        snapshot=PriceSnapshot(
            id="snp", taken_at=NOW, currency="EUR", source="test",
            prices={"S": Decimal("10")},
        ),
        scenario=base_scenario(),
        baseline=calculate(diamond),
        constraints=constraints,
    )


def test_cheapest_allowed_option_is_explained_with_vehicle_saving(diamond):
    result = recommendations(diamond)

    assert len(result) == 1
    item = result[0]
    assert (item.recommended_supplier_id, item.recommended_plant_id) == (
        "SUP-IT", "PLT-TR"
    )
    assert item.recommended_origin == "TR"
    assert item.affected_quantity == Decimal("23")
    assert item.estimated_saving == Decimal("23.000000")
    assert not item.required_by_constraint


def test_forbidden_origin_is_never_recommended(diamond):
    result = recommendations(
        diamond, SourcingConstraints(forbidden_origins=frozenset({"TR"}))
    )

    assert result == ()


def test_constraint_can_force_a_more_expensive_allowed_option(diamond):
    scenario = replace(
        base_scenario(),
        parameters=(
            ScenarioParameter("S", supplier_id="SUP-IT", plant_id="PLT-TR"),
        ),
    )
    sourcing = FakeSourcingRepository().sourcing
    snapshot = PriceSnapshot(
        id="snp", taken_at=NOW, currency="EUR", source="test",
        prices={"S": Decimal("10")},
    )
    baseline = run_calculation(
        bom=diamond, scenario=scenario, snapshot=snapshot,
        resolved=resolve_unit_prices(diamond, sourcing, snapshot, scenario),
        now=NOW, calculation_id="calc-constrained",
    )

    result = recommend(
        bom=diamond, sourcing=sourcing, snapshot=snapshot, scenario=scenario,
        baseline=baseline,
        constraints=SourcingConstraints(forbidden_origins=frozenset({"TR"})),
    )

    assert result.recommendations[0].recommended_origin == "IT"
    assert result.recommendations[0].estimated_saving == Decimal("-23.000000")
    assert result.recommendations[0].required_by_constraint
    assert result.unresolved == ()


def test_a_violation_without_allowed_option_is_reported_not_skipped(diamond):
    """Toutes les usines de S sont interdites, y compris l'actuelle (IT).

    Ignorer la pièce en silence créerait une variante qui garde une provenance
    interdite, sous un nom qui laisse croire qu'elle respecte les contraintes.
    """
    result = report(
        diamond, SourcingConstraints(forbidden_origins=frozenset({"IT", "TR", "DE"}))
    )

    assert result.recommendations == ()
    assert len(result.unresolved) == 1
    unresolved = result.unresolved[0]
    assert (unresolved.part_ref, unresolved.current_origin) == ("S", "IT")
    assert "aucune option autorisée" in unresolved.reason


def test_maximum_lead_time_is_explicitly_enforced(diamond):
    sourcing = FakeSourcingRepository().sourcing
    plants = {
        supplier: tuple(
            replace(plant, lead_time_days=10 if plant.plant_id == "PLT-TR" else 2)
            for plant in candidates
        )
        for supplier, candidates in sourcing.plants.items()
    }
    sourcing = Sourcing(offers=sourcing.offers, plants=plants)
    constrained = SourcingConstraints(max_lead_time_days=5)

    assert recommend(
        bom=diamond, sourcing=sourcing,
        snapshot=PriceSnapshot(
            id="snp", taken_at=NOW, currency="EUR", source="test",
            prices={"S": Decimal("10")},
        ),
        scenario=base_scenario(), baseline=calculate(diamond),
        constraints=constrained,
    ).recommendations == ()


def test_only_selected_parts_are_applied(diamond):
    result = recommendations(diamond)
    second = replace(
        result[0],
        part_ref="T",
        parameter=replace(result[0].parameter, part_ref="T"),
    )
    result = result + (second,)
    none = apply_recommendations(
        base_scenario(), result, frozenset(), scenario_id="copy", name="Sélection"
    )
    selected = apply_recommendations(
        base_scenario(), result, frozenset({"S"}),
        scenario_id="optimized", name="Optimisé",
    )

    assert none.parameters == ()
    assert selected.parameter_for("S").plant_id == "PLT-TR"
    assert selected.parameter_for("T") is None


def test_incomplete_baseline_is_rejected_instead_of_optimizing_missing_prices(diamond):
    baseline = replace(
        calculate(diamond),
        status=CalculationStatus.INCOMPLETE,
        parts_without_price=("S",),
    )

    with pytest.raises(IncompleteBaseline, match="prix manquant"):
        recommend(
            bom=diamond,
            sourcing=FakeSourcingRepository().sourcing,
            snapshot=PriceSnapshot(
                id="snp", taken_at=NOW, currency="EUR", source="test", prices={},
            ),
            scenario=base_scenario(),
            baseline=baseline,
            constraints=SourcingConstraints(),
        )
