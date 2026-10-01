"""Exécuter un scénario : total, décomposition, contributeurs, état, empreinte.

Le moteur de domaine calcule ; ce module l'entoure de ce dont l'écran a besoin
et de ce dont la reproductibilité a besoin.

Deux grandeurs ne se confondent jamais : la **contribution propre**, seule à se
sommer au total, et le coût unitaire complet, qui s'affiche sur une ligne
d'arbre. Additionner les secondes reviendrait à compter chaque ensemble puis son
contenu.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Mapping

from ..domain.bom import Bom
from ..domain.engine import PartLine, compute
from ..domain.prices import PriceSnapshot, SnapshotStatus
from ..domain.scenario import CalculationInput
from .price_resolution import PriceExplanation, ResolvedPrices
from .scenario import Scenario

#: Entre dans l'empreinte des entrées : la changer rend obsolètes les calculs
#: produits par une version précédente. 0.2.0 ajoute le CO2.
ENGINE_VERSION = "engine-0.2.0"
RULES_VERSION = "rules-1"
PERCENT = Decimal("0.1")


class CalculationStatus(str, Enum):
    OK = "OK"
    #: Le total est produit, mais les prix ne sont pas frais : repli après
    #: panne, ou snapshot périmé. La ligne et le total le disent à l'écran.
    DEGRADED = "DEGRADED"
    #: Il manque au moins un prix. Ce n'est pas un total fiable, et les pièces
    #: concernées sont nommées plutôt que remplacées par zéro.
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


class PriceStatus(str, Enum):
    """D'où vient le prix d'une ligne, dit sur la ligne elle-même.

    Une ligne a un seul statut : sans prix, elle est `MISSING` même si la
    valeur reçue avait d'abord été refusée — il n'y a rien de retenu à montrer.
    """

    OK = "OK"
    #: Absente de la réponse de l'API : le dernier prix connu a été retenu.
    FALLBACK = "FALLBACK"
    #: Reçue mais refusée (journal de quarantaine) : le dernier prix sain a été
    #: retenu à la place.
    QUARANTINED = "QUARANTINED"
    #: Aucun prix. Jamais remplacé par zéro.
    MISSING = "MISSING"


#: Les clés de `issue_counts`, telles que docs/api.md §4.1 les nomme.
ISSUE_KEYS = {
    PriceStatus.MISSING: "missing_price",
    PriceStatus.QUARANTINED: "quarantined",
    PriceStatus.FALLBACK: "fallback",
}


@dataclass(frozen=True)
class SystemTotal:
    system: str
    cost: Decimal
    share_pct: Decimal
    co2: Decimal = Decimal(0)
    co2_share_pct: Decimal = Decimal("0.0")


@dataclass(frozen=True)
class Contributor:
    part_ref: str
    label: str
    system: str
    cumulative_quantity: Decimal
    own_contribution: Decimal
    share_pct: Decimal
    #: Un chemin où la trouver, pour que l'écran puisse déplier jusqu'à elle.
    first_path: str


@dataclass(frozen=True)
class Co2Contributor:
    part_ref: str
    label: str
    system: str
    cumulative_quantity: Decimal
    own_co2_contribution: Decimal
    share_pct: Decimal
    first_path: str


@dataclass(frozen=True)
class Calculation:
    id: str
    scenario_id: str
    bom_version: str
    snapshot_id: str
    snapshot_age: timedelta
    snapshot_status: str
    engine_version: str
    rules_version: str
    active_rules: tuple[str, ...]
    display_currency: str
    status: CalculationStatus
    total_cost: Decimal
    computed_at: datetime
    input_digest: str
    lines: tuple[PartLine, ...]
    systems: tuple[SystemTotal, ...]
    top_contributors: tuple[Contributor, ...]
    parts_without_price: tuple[str, ...]
    explanations: dict[str, PriceExplanation]
    #: Les lignes dont le prix n'est pas `OK`, et elles seules.
    price_statuses: Mapping[str, PriceStatus] = field(default_factory=dict)
    path_own_unit_costs: Mapping[str, Decimal | None] = field(default_factory=dict)
    path_full_unit_costs: Mapping[str, Decimal | None] = field(default_factory=dict)
    total_co2: Decimal | None = None
    part_own_unit_costs: Mapping[str, Decimal | None] = field(default_factory=dict)
    part_full_unit_costs: Mapping[str, Decimal | None] = field(default_factory=dict)
    top_co2_contributors: tuple[Co2Contributor, ...] = ()

    @property
    def lines_by_ref(self) -> dict[str, PartLine]:
        return {line.part_ref: line for line in self.lines}

    @property
    def parts_without_co2(self) -> tuple[str, ...]:
        """Les pièces dont le CO2 propre est inconnu.

        Relu des lignes plutôt que stocké : la contribution NULL en base dit
        déjà la même chose. Vide pour un calcul enregistré avant que le moteur
        ne porte le CO2 — il n'a pas de CO2 du tout, pas un CO2 partiel.
        """
        if self.total_co2 is None:
            return ()
        return tuple(
            sorted(
                line.part_ref
                for line in self.lines
                if line.own_co2_contribution is None
            )
        )

    @property
    def co2_is_complete(self) -> bool:
        """Le total CO2 est celui du véhicule, pas une somme partielle."""
        return self.total_co2 is not None and not self.parts_without_co2

    def price_status_of(self, part_ref: str) -> PriceStatus:
        return self.price_statuses.get(part_ref, PriceStatus.OK)

    def issue_counts(self) -> dict[str, int]:
        counts = {key: 0 for key in ISSUE_KEYS.values()}
        for status in self.price_statuses.values():
            counts[ISSUE_KEYS[status]] += 1
        return counts


def run_calculation(
    *,
    bom: Bom,
    scenario: Scenario,
    snapshot: PriceSnapshot,
    resolved: ResolvedPrices,
    now: datetime,
    calculation_id: str,
    snapshot_is_fallback: bool = False,
    top: int = 15,
) -> Calculation:
    result = compute(
        CalculationInput(
            bom=bom,
            unit_prices=resolved.prices,
            labour_rate=scenario.labour_rate,
            active_rules=scenario.active_rules,
            unit_prices_by_path=resolved.path_prices,
            labour_minutes_by_part={
                parameter.part_ref: parameter.labour_minutes
                for parameter in scenario.parameters
                if parameter.scope == "part" and parameter.labour_minutes is not None
            },
            labour_minutes_by_path={
                parameter.path: scenario.parameter_for(
                    parameter.part_ref, parameter.path
                ).labour_minutes
                for parameter in scenario.parameters
                if parameter.scope == "path"
                and scenario.parameter_for(parameter.part_ref, parameter.path).labour_minutes
                is not None
            },
            transport_co2_per_kg=resolved.transport_co2_per_kg,
            transport_co2_per_kg_by_path=resolved.path_transport_co2_per_kg,
        )
    )

    total = result.total_cost
    first_paths = first_path_of_each_part(bom)

    return Calculation(
        id=calculation_id,
        scenario_id=scenario.id,
        bom_version=scenario.bom_version,
        snapshot_id=snapshot.id,
        snapshot_age=snapshot.age(now),
        snapshot_status=snapshot.status(now).value,
        engine_version=ENGINE_VERSION,
        rules_version=RULES_VERSION,
        active_rules=tuple(sorted(scenario.active_rules)),
        display_currency=scenario.display_currency,
        status=_status(result.parts_without_price, snapshot, now, snapshot_is_fallback),
        total_cost=total,
        total_co2=result.total_co2,
        computed_at=now,
        input_digest=input_digest(scenario, snapshot),
        lines=result.lines,
        systems=_systems(bom, result.lines, total, result.total_co2),
        top_contributors=_contributors(bom, result.lines, total, first_paths, top),
        top_co2_contributors=_co2_contributors(
            bom, result.lines, result.total_co2, first_paths, top
        ),
        parts_without_price=result.parts_without_price,
        explanations=resolved.explanations,
        price_statuses=_price_statuses(
            snapshot, resolved, result.parts_without_price
        ),
        path_own_unit_costs=result.path_own_unit_costs,
        path_full_unit_costs=result.path_full_unit_costs,
        part_own_unit_costs=result.part_own_unit_costs,
        part_full_unit_costs=result.part_full_unit_costs,
    )


def _price_statuses(
    snapshot: PriceSnapshot, resolved: ResolvedPrices, missing: tuple[str, ...]
) -> dict[str, PriceStatus]:
    statuses = {ref: PriceStatus.MISSING for ref in missing}
    for ref, explanation in resolved.explanations.items():
        # Un prix forcé remplace celui du snapshot : ce qui est arrivé à ce
        # dernier ne dit plus rien du montant affiché.
        if explanation.is_overridden:
            continue
        if ref in snapshot.quarantined_refs:
            statuses[ref] = PriceStatus.QUARANTINED
        elif ref in snapshot.fallback_refs:
            statuses[ref] = PriceStatus.FALLBACK
    return statuses


def with_contributors(calculation: Calculation, bom: Bom, top: int = 15) -> Calculation:
    """Reconstitue les contributeurs d'un calcul relu en base.

    Ils ne sont pas stockés : ce sont les mêmes lignes, triées, avec les
    libellés de la nomenclature. Une donnée dupliquée finit par diverger de
    celle dont elle est tirée.
    """
    from dataclasses import replace

    first_paths = first_path_of_each_part(bom)
    return replace(
        calculation,
        top_contributors=_contributors(
            bom, calculation.lines, calculation.total_cost, first_paths, top
        ),
        top_co2_contributors=_co2_contributors(
            bom, calculation.lines, calculation.total_co2, first_paths, top
        ),
    )


def input_digest(scenario: Scenario, snapshot: PriceSnapshot) -> str:
    """L'empreinte des entrées, et d'elles seules.

    Ni l'identifiant du calcul, ni l'horloge n'y entrent : deux calculs
    identiques doivent se reconnaître, sinon l'écran marquerait les totaux
    obsolètes sans raison.
    """
    payload = {
        "bom_version": scenario.bom_version,
        "snapshot_id": snapshot.id,
        "display_currency": scenario.display_currency,
        "labour_rate": str(scenario.labour_rate),
        "active_rules": sorted(scenario.active_rules),
        "engine_version": ENGINE_VERSION,
        "rules_version": RULES_VERSION,
        "parameters": sorted(
            (
                parameter.part_ref,
                parameter.scope,
                parameter.path or "",
                parameter.supplier_id or "",
                parameter.plant_id or "",
                str(parameter.price_override or ""),
                str(parameter.labour_minutes or ""),
            )
            for parameter in scenario.parameters
        ),
    }
    purchase_currencies = sorted(
        (p.part_ref, p.scope, p.path or "", p.purchase_currency)
        for p in scenario.parameters if p.purchase_currency is not None
    )
    # Un réglage sauvegardé doit rendre les anciens totaux obsolètes. L'ajout
    # conditionnel conserve les empreintes des scénarios antérieurs sans devise
    # d'achat explicite ; il ne réalise aucune conversion de prix.
    if purchase_currencies:
        payload["purchase_currencies"] = purchase_currencies
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _status(
    missing: tuple[str, ...],
    snapshot: PriceSnapshot,
    now: datetime,
    is_fallback: bool,
) -> CalculationStatus:
    if missing:
        return CalculationStatus.INCOMPLETE
    if is_fallback or snapshot.status(now) is not SnapshotStatus.FRESH:
        return CalculationStatus.DEGRADED
    return CalculationStatus.OK


def _share(part: Decimal, total: Decimal) -> Decimal:
    """Pourcentage à une décimale.

    Arrondis, les pourcentages peuvent totaliser 99,9 ou 100,1 : c'est assumé
    (ADR-0011). Le critère d'acceptation porte sur les montants, qui somment
    exactement.
    """
    if total == 0:
        return Decimal("0.0")
    return (part / total * 100).quantize(PERCENT, rounding=ROUND_HALF_UP)


def _systems(
    bom: Bom, lines, total: Decimal, total_co2: Decimal | None
) -> tuple[SystemTotal, ...]:
    costs: dict[str, Decimal] = {}
    co2s: dict[str, Decimal] = {}
    for line in lines:
        system = bom.parts[line.part_ref].system
        if line.own_contribution is not None:
            costs[system] = costs.get(system, Decimal(0)) + line.own_contribution
        if line.own_co2_contribution is not None:
            co2s[system] = co2s.get(system, Decimal(0)) + line.own_co2_contribution

    systems = sorted(set(costs) | set(co2s))
    return tuple(
        SystemTotal(
            system=system,
            cost=costs.get(system, Decimal(0)),
            share_pct=_share(costs.get(system, Decimal(0)), total),
            co2=co2s.get(system, Decimal(0)),
            co2_share_pct=(
                _share(co2s.get(system, Decimal(0)), total_co2)
                if total_co2 is not None
                else Decimal("0.0")
            ),
        )
        for system in systems
    )


def _contributors(
    bom: Bom, lines, total: Decimal, first_paths: dict[str, str], top: int
) -> tuple[Contributor, ...]:
    ranked = sorted(
        (line for line in lines if line.own_contribution is not None),
        key=lambda line: (-line.own_contribution, line.part_ref),
    )
    return tuple(
        Contributor(
            part_ref=line.part_ref,
            label=bom.parts[line.part_ref].label,
            system=bom.parts[line.part_ref].system,
            cumulative_quantity=line.cumulative_quantity,
            own_contribution=line.own_contribution,
            share_pct=_share(line.own_contribution, total),
            first_path=first_paths.get(line.part_ref, line.part_ref),
        )
        for line in ranked[:top]
    )


def _co2_contributors(
    bom: Bom,
    lines,
    total_co2: Decimal | None,
    first_paths: dict[str, str],
    top: int,
) -> tuple[Co2Contributor, ...]:
    if total_co2 is None:
        return ()
    ranked = sorted(
        (line for line in lines if line.own_co2_contribution is not None),
        key=lambda line: (-line.own_co2_contribution, line.part_ref),
    )
    return tuple(
        Co2Contributor(
            part_ref=line.part_ref,
            label=bom.parts[line.part_ref].label,
            system=bom.parts[line.part_ref].system,
            cumulative_quantity=line.cumulative_quantity,
            own_co2_contribution=line.own_co2_contribution,
            share_pct=_share(line.own_co2_contribution, total_co2),
            first_path=first_paths.get(line.part_ref, line.part_ref),
        )
        for line in ranked[:top]
    )


def first_path_of_each_part(bom: Bom) -> dict[str, str]:
    """Un chemin par pièce, le premier rencontré en descendant.

    Il ne s'agit pas de désigner « le bon » emplacement — il n'y en a pas — mais
    d'en donner un pour que l'écran puisse déplier jusqu'à la pièce.
    """
    paths: dict[str, str] = {bom.root_ref: bom.root_ref}
    for ref in bom.topological_order():
        for child_ref, _ in bom.children_of(ref):
            paths.setdefault(child_ref, f"{paths[ref]}/{child_ref}")
    return paths
