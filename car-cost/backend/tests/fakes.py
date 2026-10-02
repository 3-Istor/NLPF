"""Dépôts en mémoire.

Ils permettent de tester les routes sans Postgres. Ils respectent les mêmes
interdits que la base — un snapshot ne se modifie pas — parce qu'un double
plus permissif que le vrai laisserait passer des bogues.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from carcost.application.ports import (
    BomVersionNotFound,
    BomVersionNotValidated,
    CalculationNotFound,
    CalculationSnapshotNotFound,
    PriceSnapshotNotFound,
    QuarantineRecord,
    ScenarioNotFound,
    SnapshotNameTaken,
)
from carcost.application.scenario import (
    Plant, Scenario, ScenarioParameter, Sourcing, SupplierOffer,
)
from carcost.domain.calculation_snapshot import name_key


class FakeBomRepository:
    def __init__(self, bom, version: str = "bom-test", validated: bool = True):
        self.bom = bom
        self.version = version
        self.validated = validated

    def load(self, version: str):
        if version != self.version:
            raise BomVersionNotFound(version)
        if not self.validated:
            raise BomVersionNotValidated(version)
        return self.bom

    def versions(self):
        return ()


class FakeSourcingRepository:
    def __init__(self, sourcing: Sourcing | None = None):
        self.sourcing = sourcing or _default_sourcing()

    def load(self, bom_version: str) -> Sourcing:
        return self.sourcing


def _default_sourcing() -> Sourcing:
    return Sourcing(
        offers={
            "S": (
                SupplierOffer("SUP-IT", Decimal("1.000000"), is_default=True),
                SupplierOffer("SUP-DE", Decimal("1.200000"), is_default=False),
            )
        },
        plants={
            "SUP-IT": (
                Plant("PLT-IT", "SUP-IT", "IT", Decimal("1.000000"),
                      Decimal("0.021000"), is_default=True),
                Plant("PLT-TR", "SUP-IT", "TR", Decimal("0.900000"),
                      Decimal("0.142000"), is_default=False),
            ),
            "SUP-DE": (
                Plant("PLT-DE", "SUP-DE", "DE", Decimal("1.000000"),
                      Decimal("0.046000"), is_default=True),
            ),
        },
    )


class FakeSnapshotRepository:
    def __init__(self, *snapshots):
        self.snapshots = list(snapshots)
        self.journals: dict[str, tuple[QuarantineRecord, ...]] = {}

    def latest(self):
        return self.snapshots[-1] if self.snapshots else None

    def list_all(self):
        return tuple(reversed(self.snapshots))

    def get(self, snapshot_id: str):
        for snapshot in self.snapshots:
            if snapshot.id == snapshot_id:
                return snapshot
        raise PriceSnapshotNotFound(snapshot_id)

    def save(self, snapshot, quarantined=(), previous_id=None) -> None:
        if any(existing.id == snapshot.id for existing in self.snapshots):
            raise AssertionError("un snapshot enregistré ne se réécrit pas")
        self.snapshots.append(snapshot)
        self.journals[snapshot.id] = tuple(
            QuarantineRecord(
                part_ref=entry.part_ref,
                currency=snapshot.currency,
                rejected_value=entry.rejected_value,
                reason=entry.reason,
                replacement=entry.replacement,
                replacement_from_snapshot=(
                    previous_id if entry.replacement is not None else None
                ),
                detected_at=snapshot.taken_at,
            )
            for entry in quarantined
        )

    def quarantine_of(self, snapshot_id: str):
        self.get(snapshot_id)
        return self.journals.get(snapshot_id, ())


class FakeScenarioRepository:
    def __init__(self):
        self.scenarios: dict[str, Scenario] = {}
        self._sequence = 0
        self._ids: dict[str, tuple[str, ScenarioParameter]] = {}

    def create(self, scenario: Scenario) -> None:
        if scenario.id in self.scenarios:
            raise AssertionError("un scénario créé doit avoir sa propre identité")
        self.scenarios[scenario.id] = replace(scenario, parameters=())
        for parameter in scenario.parameters:
            self.put_parameter(scenario.id, parameter)

    def get(self, scenario_id: str) -> Scenario:
        try:
            return self.scenarios[scenario_id]
        except KeyError as missing:
            raise ScenarioNotFound(scenario_id) from missing

    def list_all(self) -> tuple[Scenario, ...]:
        return tuple(reversed(tuple(self.scenarios.values())))

    def delete(self, scenario_id: str) -> None:
        self.get(scenario_id)
        del self.scenarios[scenario_id]
        self._ids = {
            identifier: entry
            for identifier, entry in self._ids.items()
            if entry[0] != scenario_id
        }

    def parameter_ids(self, scenario_id: str) -> dict[tuple[str, str], str]:
        self.get(scenario_id)
        return {
            (parameter.part_ref, parameter.path or ""): identifier
            for identifier, (owner, parameter) in self._ids.items()
            if owner == scenario_id
        }

    def put_parameter(self, scenario_id: str, parameter) -> str:
        scenario = self.get(scenario_id)
        kept = tuple(
            existing
            for existing in scenario.parameters
            if not (
                existing.part_ref == parameter.part_ref
                and existing.scope == parameter.scope
                and (existing.path or "") == (parameter.path or "")
            )
        )
        identifier = next((
            identifier for identifier, (owner, existing) in self._ids.items()
            if owner == scenario_id and existing.part_ref == parameter.part_ref
            and existing.scope == parameter.scope and existing.path == parameter.path
        ), None)
        if identifier is None:
            self._sequence += 1
            identifier = f"prm-{self._sequence}"
        self.scenarios[scenario_id] = replace(
            scenario, parameters=kept + (parameter,)
        )
        self._ids[identifier] = (scenario_id, parameter)
        return identifier

    def delete_parameter(self, scenario_id: str, parameter_id: str) -> None:
        scenario = self.get(scenario_id)
        entry = self._ids.get(parameter_id)
        if entry is None or entry[0] != scenario_id:
            return
        _, parameter = self._ids.pop(parameter_id)
        self.scenarios[scenario_id] = replace(
            scenario,
            parameters=tuple(p for p in scenario.parameters if p is not parameter),
        )


class FakeCalculationRepository:
    def __init__(self):
        self.calculations: dict[str, object] = {}
        self.order: list[str] = []

    def save(self, calculation) -> None:
        if calculation.id in self.calculations:
            raise AssertionError("un calcul enregistré ne se réécrit pas")
        self.calculations[calculation.id] = calculation
        self.order.append(calculation.id)

    def get(self, calculation_id: str):
        try:
            return self.calculations[calculation_id]
        except KeyError as missing:
            raise CalculationNotFound(calculation_id) from missing

    def latest_for(self, scenario_id: str):
        for identifier in reversed(self.order):
            calculation = self.calculations[identifier]
            if calculation.scenario_id == scenario_id:
                return calculation
        return None


class FakeCalculationSnapshotRepository:
    """Sans méthode de suppression, comme la base : un snapshot reste."""

    def __init__(self):
        self.snapshots: dict[str, object] = {}
        self.order: list[str] = []
        self.history: dict[str, list[tuple[str, object]]] = {}

    def save(self, snapshot) -> None:
        if snapshot.id in self.snapshots:
            raise AssertionError("un snapshot de calcul enregistré ne se réécrit pas")
        self._ensure_free(snapshot.name, snapshot.bom_version, snapshot.id)
        self.snapshots[snapshot.id] = snapshot
        self.order.append(snapshot.id)
        self.history[snapshot.id] = [(snapshot.name, snapshot.created_at)]

    def get(self, snapshot_id: str):
        try:
            return self.snapshots[snapshot_id]
        except KeyError as missing:
            raise CalculationSnapshotNotFound(snapshot_id) from missing

    def list_for(self, bom_version: str):
        return tuple(
            self.snapshots[identifier]
            for identifier in reversed(self.order)
            if self.snapshots[identifier].bom_version == bom_version
        )

    def for_scenario(self, scenario_id: str):
        return tuple(
            self.snapshots[identifier]
            for identifier in reversed(self.order)
            if self.snapshots[identifier].scenario_id == scenario_id
        )

    def rename(self, snapshot_id: str, name: str, renamed_at) -> None:
        snapshot = self.get(snapshot_id)
        self._ensure_free(name, snapshot.bom_version, snapshot_id)
        self.snapshots[snapshot_id] = replace(snapshot, name=name)
        self.history[snapshot_id].append((name, renamed_at))

    def name_history(self, snapshot_id: str):
        self.get(snapshot_id)
        return tuple(self.history[snapshot_id])

    def _ensure_free(self, name: str, bom_version: str, own_id: str) -> None:
        # L'index unique de la base : la même clé, dans la même version.
        for existing in self.list_for(bom_version):
            if existing.id != own_id and existing.name_key == name_key(name):
                raise SnapshotNameTaken(name, existing.id)
