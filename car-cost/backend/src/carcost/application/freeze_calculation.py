"""Figer un calcul sous un nom, le renommer, comparer deux gels (ADR-0014).

Figer, c'est lancer un calcul maintenant et en copier les hypothèses dans la
même opération : on ne fige jamais un vieux calcul, donc il n'y a pas de refus
« obsolète ». Un calcul `INCOMPLETE` se fige et garde son statut.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from typing import Callable

from ..domain.calculation_snapshot import (
    CalculationSnapshot, FrozenParameter, name_key, snapshot_name,
)
from .compare_scenarios import ScenarioComparison, compare_calculations
from .ports import (
    BomRepository, CalculationRepository, CalculationSnapshotRepository,
    ScenarioRepository, SnapshotNameTaken,
)
from .run_calculation import Calculation
from .scenario import Scenario, ScenarioParameter

_FROZEN_FIELDS = tuple(field.name for field in fields(FrozenParameter))


def freeze_scenario(
    scenario_id: str,
    name: str,
    *,
    scenarios: ScenarioRepository,
    boms: BomRepository,
    snapshots_repo: CalculationSnapshotRepository,
    calculate: Callable[[Scenario], Calculation],
    snapshot_id: str,
    now: datetime,
) -> CalculationSnapshot:
    name = snapshot_name(name)
    scenario = scenarios.get(scenario_id)
    boms.load(scenario.bom_version)
    # Tout refus passe avant le calcul : un gel refusé ne laisse pas derrière
    # lui un calcul enregistré que personne n'a demandé.
    _ensure_free(name, scenario.bom_version, snapshots_repo, own_id=None)

    calculation = calculate(scenario)
    # La copie vient de l'objet calculé, jamais d'une relecture : le scénario
    # vivant a pu changer entre-temps, et la copie doit expliquer ce total-là.
    snapshot = CalculationSnapshot(
        id=snapshot_id,
        name=name,
        bom_version=scenario.bom_version,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        calculation_id=calculation.id,
        price_snapshot_id=calculation.snapshot_id,
        display_currency=scenario.display_currency,
        labour_rate=scenario.labour_rate,
        active_rules=scenario.active_rules,
        parameters=tuple(_frozen(p) for p in scenario.parameters),
        created_at=now,
        derived_from=scenario.derived_from,
    )
    snapshots_repo.save(snapshot)
    return snapshot


def rename_snapshot(
    snapshot_id: str,
    name: str,
    *,
    snapshots_repo: CalculationSnapshotRepository,
    now: datetime,
) -> CalculationSnapshot:
    name = snapshot_name(name)
    snapshot = snapshots_repo.get(snapshot_id)
    _ensure_free(name, snapshot.bom_version, snapshots_repo, own_id=snapshot.id)
    snapshots_repo.rename(snapshot_id, name, now)
    return snapshots_repo.get(snapshot_id)


def compare_snapshots(
    a_id: str,
    b_id: str,
    *,
    snapshots_repo: CalculationSnapshotRepository,
    calculations: CalculationRepository,
) -> tuple[ScenarioComparison, CalculationSnapshot, CalculationSnapshot]:
    """Compare les calculs figés tels quels : ni recalcul, ni enregistrement.

    Les refus sont ceux de la comparaison de scénarios (ADR-0012) : snapshots
    de prix différents, ou calcul incomplet.
    """
    snapshot_a = snapshots_repo.get(a_id)
    snapshot_b = snapshots_repo.get(b_id)
    comparison = compare_calculations(
        calculations.get(snapshot_a.calculation_id),
        calculations.get(snapshot_b.calculation_id),
    )
    return comparison, snapshot_a, snapshot_b


def _frozen(parameter: ScenarioParameter) -> FrozenParameter:
    return FrozenParameter(
        **{name: getattr(parameter, name) for name in _FROZEN_FIELDS}
    )


def _ensure_free(
    name: str,
    bom_version: str,
    snapshots_repo: CalculationSnapshotRepository,
    *,
    own_id: str | None,
) -> None:
    key = name_key(name)
    for existing in snapshots_repo.list_for(bom_version):
        if existing.id != own_id and existing.name_key == key:
            raise SnapshotNameTaken(name, existing.id)
