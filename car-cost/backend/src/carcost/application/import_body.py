"""Importer une variante de carrosserie et la chiffrer (ADR-0017 §6, §8 et §9).

Les règles sont dans `body_import` ; ici, l'ordre des lectures et des
écritures. Tout est calculé avant la première écriture : un refus, un prix
introuvable ou des prix incomplets ne laissent rien derrière eux.

L'écart est toujours `compare_calculations(A, B).cost_delta`, A et B sur le
même snapshot, celui de l'origine de la filiation. Sans snapshot, pas
d'écart : jamais 0 €.
"""

from __future__ import annotations

from dataclasses import astuple, dataclass
from decimal import Decimal
from hashlib import sha256

from ..domain.bom import Bom
from .body_import import PartChange, diff_versions, plan_variant
from .compare_scenarios import compare_calculations
from .ports import ModelNotFound, NewVariant, VariantIdCollision
from .price_resolution import resolve_unit_prices
from .run_calculation import Calculation, CalculationStatus, run_calculation
from .scenario import Scenario


class IncompletePrices(Exception):
    """Un prix manque dans le snapshot : on ne chiffre pas d'écart (ADR-0017)."""

    def __init__(self, parts_without_price: tuple[str, ...], snapshot_id: str):
        self.parts_without_price = parts_without_price
        self.snapshot_id = snapshot_id
        super().__init__(
            f"calcul incomplet sur le snapshot {snapshot_id}, pièces sans prix : "
            + ", ".join(parts_without_price)
        )


@dataclass(frozen=True)
class CostedChange(PartChange):
    """Un changement, avec ce que le serveur lit pour l'écran : jamais le navigateur."""

    cumulative_quantity: Decimal
    #: `None` sans snapshot, et avant pour une pièce nouvelle.
    unit_cost_before: Decimal | None = None
    unit_cost_after: Decimal | None = None


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
    changes: tuple[CostedChange, ...]
    cost: CostDelta | None
    cost_status: str  # "OK" | "NO_PRICES"
    #: Écart de quantité de matière des pièces mesurées (R1), fixations non comprises.
    material_mass_delta_kg: Decimal


@dataclass(frozen=True)
class BodyChanges:
    version: str
    parent_version: str | None
    changes: tuple[CostedChange, ...]
    cost: CostDelta | None
    cost_status: str
    material_mass_delta_kg: Decimal


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
        return ImportOutcome("NO_CHANGE", version, None, None, None, (), cost, _status(cost), Decimal(0))

    digest = sha256(data).hexdigest()
    variant_id = f"{version}+{digest[:8]}"
    label = f"{summary.label} — variante {digest[:8]}"
    if any(known.id == variant_id for known in boms.versions()):
        if models.get(variant_id).sha256 != digest:
            raise VariantIdCollision(variant_id)
        variant = boms.load(variant_id)
        priced = _priced(variant, _neutral("body-import-b", variant_id, summary), sourcing.load(version), snapshot, now)
        cost = _delta(reference, priced)
        changes = _costed(diff_versions(parent, variant), variant, reference, priced)
        return ImportOutcome(
            "ALREADY_IMPORTED", version, variant_id, label, None, changes, cost, _status(cost),
            _mass_delta(changes),
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
    changes = _costed(plan.changes, plan.bom, reference, priced)
    return ImportOutcome(
        "CREATED", version, variant_id, label, scenario.id, changes, cost, _status(cost), _mass_delta(changes),
    )


def body_changes(version: str, *, boms, sourcing, snapshots, clock) -> BodyChanges:
    variant = boms.load(version)
    parent_id = _summary(version, boms).parent_version_id
    if parent_id is None:
        return BodyChanges(version, None, (), None, "OK", Decimal(0))
    parent = boms.load(parent_id)
    summary = _summary(parent_id, boms)
    snapshot = snapshots.latest(price_origin(version, boms))
    now = clock()
    before = _priced(parent, _neutral("body-changes-a", parent_id, summary), sourcing.load(parent_id), snapshot, now)
    after = _priced(variant, _neutral("body-changes-b", version, summary), sourcing.load(version), snapshot, now)
    cost = _delta(before, after)
    changes = _costed(diff_versions(parent, variant), variant, before, after)
    return BodyChanges(version, parent_id, changes, cost, _status(cost), _mass_delta(changes))


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
    if CalculationStatus.INCOMPLETE in (a.status, b.status):
        raise IncompletePrices(tuple(sorted(set(a.parts_without_price) | set(b.parts_without_price))), a.snapshot_id)
    comparison = compare_calculations(a, b)
    return CostDelta(comparison.snapshot_id, comparison.total_a, comparison.total_b, comparison.cost_delta)


def _costed(changes, bom: Bom, before: Calculation | None, after: Calculation | None) -> tuple[CostedChange, ...]:
    cumulative = {ref: Decimal(0) for ref in bom.parts}
    cumulative[bom.root_ref] = Decimal(1)
    for ref in bom.topological_order():
        for child, quantity in bom.children_of(ref):
            cumulative[child] += cumulative[ref] * quantity

    def unit_costs(calculation):
        return {} if calculation is None else {l.part_ref: l.full_unit_cost for l in calculation.lines}

    costs_before, costs_after = unit_costs(before), unit_costs(after)
    return tuple(
        CostedChange(*astuple(c), cumulative[c.part_ref], costs_before.get(c.part_ref), costs_after.get(c.part_ref))
        for c in changes
    )


def _mass_delta(changes) -> Decimal:
    return sum((c.mass_delta_kg * c.cumulative_quantity for c in changes), Decimal(0))


def _status(cost: CostDelta | None) -> str:
    return "OK" if cost is not None else "NO_PRICES"
