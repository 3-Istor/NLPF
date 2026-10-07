"""Importer une variante de carrosserie et la chiffrer (ADR-0017 §6, §8 et §9).

Les règles sont dans `body_import` ; ici, l'ordre des lectures et des
écritures. Tout est calculé avant la première écriture : un refus, un prix
introuvable ou un calcul incomparable ne laissent rien derrière eux.

L'écart est toujours `compare_calculations(A, B).cost_delta`, A et B sur le
même snapshot, celui de l'origine de la filiation. Sans snapshot, pas
d'écart : jamais 0 €.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from ..domain.bom import Bom
from .body_import import PartChange, diff_versions, plan_variant
from .compare_scenarios import compare_calculations
from .ports import ModelNotFound, NewVariant, VariantIdCollision
from .price_resolution import resolve_unit_prices
from .run_calculation import Calculation, run_calculation
from .scenario import Scenario


@dataclass(frozen=True)
class CostDelta:
    snapshot_id: str
    total_before: Decimal
    total_after: Decimal
    delta: Decimal


@dataclass(frozen=True)
class ImportOutcome:
    status: str  # "CREATED" | "ALREADY_IMPORTED" | "NO_CHANGE"
    parent_version: str
    variant_id: str | None
    variant_label: str | None
    scenario_id: str | None
    changes: tuple[PartChange, ...]
    cost: CostDelta | None
    cost_status: str  # "OK" | "NO_PRICES"


@dataclass(frozen=True)
class BodyChanges:
    version: str
    parent_version: str | None
    changes: tuple[PartChange, ...]
    cost: CostDelta | None
    cost_status: str


def price_origin(version: str, boms) -> str:
    """La racine de la filiation : c'est elle qui a des prix (ADR-0017 §8)."""
    parents = {summary.id: summary.parent_version_id for summary in boms.versions()}
    while parents.get(version):
        version = parents[version]
    return version


def import_body(
    version: str, data: bytes, *, read_model, boms, models, variants, sourcing,
    snapshots, scenarios, calculations, clock, new_id,
) -> ImportOutcome:
    parent = boms.load(version)
    if models.get(version) is None:
        raise ModelNotFound(version)
    plan = plan_variant(parent, read_model(data))

    summary = _summary(version, boms)
    snapshot = snapshots.latest(price_origin(version, boms))
    now = clock()
    reference = _priced(parent, _neutral("body-import-a", version, summary), sourcing.load(version), snapshot, now)
    if plan is None:
        cost = _delta(reference, reference)
        return ImportOutcome("NO_CHANGE", version, None, None, None, (), cost, _status(cost))

    digest = sha256(data).hexdigest()
    variant_id = f"{version}+{digest[:8]}"
    label = f"{summary.label} — variante {digest[:8]}"
    if any(known.id == variant_id for known in boms.versions()):
        if models.get(variant_id).sha256 != digest:
            raise VariantIdCollision(variant_id)
        variant = boms.load(variant_id)
        priced = _priced(variant, _neutral("body-import-b", variant_id, summary), sourcing.load(version), snapshot, now)
        cost = _delta(reference, priced)
        return ImportOutcome(
            "ALREADY_IMPORTED", version, variant_id, label, None,
            diff_versions(parent, variant), cost, _status(cost),
        )

    scenario = Scenario(
        f"scn-{new_id()}", variant_id, "EUR", summary.reference_labour_rate, name=f"Import — {label}",
    )
    # La variante n'est pas encore écrite : ses offres sont celles de la parente, recopiées.
    priced = _priced(plan.bom, scenario, sourcing.load(version), snapshot, now, f"calc-{new_id()}")
    cost = _delta(reference, priced)

    variants.save_variant(NewVariant(variant_id, label, version, digest, data, plan))
    scenarios.create(scenario)
    if priced is not None:
        calculations.save(priced)
    return ImportOutcome("CREATED", version, variant_id, label, scenario.id, plan.changes, cost, _status(cost))


def body_changes(version: str, *, boms, sourcing, snapshots, clock) -> BodyChanges:
    variant = boms.load(version)
    parent_id = _summary(version, boms).parent_version_id
    if parent_id is None:
        return BodyChanges(version, None, (), None, "OK")
    parent = boms.load(parent_id)
    summary = _summary(parent_id, boms)
    snapshot = snapshots.latest(price_origin(version, boms))
    now = clock()
    cost = _delta(
        _priced(parent, _neutral("body-changes-a", parent_id, summary), sourcing.load(parent_id), snapshot, now),
        _priced(variant, _neutral("body-changes-b", version, summary), sourcing.load(version), snapshot, now),
    )
    return BodyChanges(version, parent_id, diff_versions(parent, variant), cost, _status(cost))


def _summary(version: str, boms):
    return next(summary for summary in boms.versions() if summary.id == version)


def _neutral(scenario_id: str, version: str, parent_summary) -> Scenario:
    """Un scénario sans réglage, au taux de la parente : jamais enregistré."""
    return Scenario(scenario_id, version, "EUR", parent_summary.reference_labour_rate)


def _priced(bom: Bom, scenario: Scenario, sourcing, snapshot, now, calculation_id=None) -> Calculation | None:
    if snapshot is None:
        return None
    return run_calculation(
        bom=bom, scenario=scenario, snapshot=snapshot,
        resolved=resolve_unit_prices(bom, sourcing, snapshot, scenario),
        now=now, calculation_id=calculation_id or f"{scenario.id}-calc",
    )


def _delta(a: Calculation | None, b: Calculation | None) -> CostDelta | None:
    if a is None:
        return None
    comparison = compare_calculations(a, b)
    return CostDelta(comparison.snapshot_id, comparison.total_a, comparison.total_b, comparison.cost_delta)


def _status(cost: CostDelta | None) -> str:
    return "OK" if cost is not None else "NO_PRICES"
