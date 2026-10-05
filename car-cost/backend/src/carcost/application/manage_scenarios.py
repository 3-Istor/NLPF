"""Créer, dupliquer et régler un scénario indépendamment de ses prix."""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal

from .browse_bom import PathNotFound, children_of_path
from .ports import (
    BomRepository, CalculationSnapshotRepository, ScenarioRepository,
    SourcingRepository,
)
from .price_resolution import (
    NoSupplierForPart, PlantNotAvailableForSupplier, validate_parameters,
)
from .scenario import Scenario, ScenarioParameter, Sourcing


class InvalidScenario(Exception):
    """Un scénario dont les réglages ne peuvent pas être conservés tels quels."""


class ScenarioHasSnapshots(Exception):
    """Le scénario porte des snapshots de calcul : le supprimer est refusé.

    Les snapshots sont nommés pour que l'utilisateur sache ce qui le retient.
    """

    def __init__(self, names: tuple[str, ...]):
        super().__init__(
            "le scénario porte des snapshots de calcul : " + ", ".join(names)
        )
        self.names = names


def create_scenario(
    scenario: Scenario,
    boms: BomRepository,
    scenarios: ScenarioRepository,
    sourcing: SourcingRepository,
) -> Scenario:
    validate_scenario(scenario, boms, sourcing)
    scenarios.create(scenario)
    return scenarios.get(scenario.id)


def duplicate_scenario(
    source_id: str,
    *,
    name: str,
    scenario_id: str,
    boms: BomRepository,
    scenarios: ScenarioRepository,
    sourcing: SourcingRepository,
) -> Scenario:
    original = scenarios.get(source_id)
    if scenario_id == original.id:
        raise InvalidScenario("une copie doit avoir sa propre identité")
    copied = replace(original, id=scenario_id, name=name)
    return create_scenario(copied, boms, scenarios, sourcing)


def delete_scenario(
    scenario_id: str,
    *,
    scenarios: ScenarioRepository,
    snapshots_repo: CalculationSnapshotRepository,
) -> None:
    scenarios.get(scenario_id)
    carried = snapshots_repo.for_scenario(scenario_id)
    if carried:
        raise ScenarioHasSnapshots(tuple(snapshot.name for snapshot in carried))
    scenarios.delete(scenario_id)


def set_labour_rate(
    scenario_id: str, rate: Decimal, scenarios: ScenarioRepository,
) -> None:
    _decimal(rate, "taux horaire", scale=6, integer_digits=12)
    scenarios.set_labour_rate(scenario_id, rate)


def put_parameter(
    scenario_id: str,
    parameter: ScenarioParameter,
    boms: BomRepository,
    scenarios: ScenarioRepository,
    sourcing: SourcingRepository,
) -> str:
    scenario = scenarios.get(scenario_id)
    kept = tuple(p for p in scenario.parameters if _target(p) != _target(parameter))
    candidate = replace(scenario, parameters=kept + (parameter,))
    validate_scenario(candidate, boms, sourcing)
    return scenarios.put_parameter(scenario_id, parameter)


def validate_scenario(
    scenario: Scenario, boms: BomRepository, sourcing: SourcingRepository,
) -> None:
    if not scenario.name.strip():
        raise InvalidScenario("le nom du scénario ne peut pas être vide")
    _currency(scenario.display_currency)
    _decimal(scenario.labour_rate, "taux horaire", scale=6, integer_digits=12)
    bom = boms.load(scenario.bom_version)
    # La nomenclature validée est la source de vérité, même sans snapshot.
    validate_parameters(bom, scenario)
    targets = set()
    catalogue = None
    for parameter in scenario.parameters:
        if parameter.scope not in ("part", "path"):
            raise InvalidScenario(f"portée inconnue : {parameter.scope}")
        if parameter.scope == "part" and parameter.path is not None:
            raise InvalidScenario("une portée pièce ne porte pas de chemin")
        if parameter.scope == "path":
            if not parameter.path or parameter.path.split("/")[-1] != parameter.part_ref:
                raise InvalidScenario("le chemin doit se terminer par la référence ciblée")
            try:
                children_of_path(bom, parameter.path, limit=0)
            except PathNotFound as error:
                raise InvalidScenario(str(error)) from error
        target = _target(parameter)
        if target in targets:
            raise InvalidScenario(f"plusieurs paramètres pour la même cible : {target}")
        targets.add(target)
        if parameter.purchase_currency is not None:
            _currency(parameter.purchase_currency)
        if parameter.price_override is not None:
            _decimal(parameter.price_override, "prix forcé", scale=6, integer_digits=12)
        if parameter.labour_minutes is not None:
            _decimal(
                parameter.labour_minutes, "temps de main-d'œuvre",
                scale=4, integer_digits=8,
            )
        if parameter.labour_rate is not None:
            _decimal(parameter.labour_rate, "taux horaire", scale=6, integer_digits=12)
        if parameter.plant_id is not None and parameter.supplier_id is None:
            raise InvalidScenario("un choix d'usine doit porter son fournisseur")
        if parameter.supplier_id is not None:
            if catalogue is None:
                catalogue = sourcing.load(scenario.bom_version)
            _validate_sourcing(parameter, catalogue)


def _target(parameter: ScenarioParameter) -> tuple:
    return parameter.part_ref, parameter.scope, parameter.path


def _validate_sourcing(parameter: ScenarioParameter, sourcing: Sourcing) -> None:
    if sourcing.offer(parameter.part_ref, parameter.supplier_id) is None:
        raise NoSupplierForPart(
            f"{parameter.part_ref} : fournisseur « {parameter.supplier_id} » indisponible"
        )
    if parameter.plant_id is not None and sourcing.plant(
        parameter.supplier_id, parameter.plant_id,
    ) is None:
        raise PlantNotAvailableForSupplier(
            f"l'usine {parameter.plant_id} n'appartient pas au fournisseur {parameter.supplier_id}"
        )


def _currency(value: str) -> None:
    if re.fullmatch(r"[A-Z]{3}", value) is None:
        raise InvalidScenario(f"code de devise invalide : {value}")


def _decimal(
    value: Decimal, label: str, *, scale: int, integer_digits: int,
    nonnegative: bool = True,
) -> None:
    # NUMERIC arrondit silencieusement au-delà de son échelle : refuser plutôt
    # que promettre un aller-retour exact et enregistrer une autre valeur.
    if not value.is_finite():
        raise InvalidScenario(f"{label} doit être un nombre fini")
    if value.copy_abs() >= Decimal(10) ** integer_digits:
        raise InvalidScenario(f"{label} dépasse la capacité de stockage")
    if value != value.quantize(Decimal(1).scaleb(-scale)):
        raise InvalidScenario(f"{label} ne peut pas dépasser {scale} décimales")
    if nonnegative and value < 0:
        raise InvalidScenario(f"{label} ne peut pas être négatif")
