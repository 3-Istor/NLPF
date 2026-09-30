"""Le moteur de coût : programmation dynamique en ordre topologique (ADR-0005).

Deux parcours de sens opposés, et c'est voulu :

  - les **quantités cumulées** descendent, des parents vers les enfants ;
  - les **coûts unitaires** remontent, des enfants vers les parents.

Sans surcharge de chemin, chaque pièce est évaluée exactement une fois. Avec
une surcharge, seuls ses préfixes reçoivent un contexte supplémentaire, comme
le prescrit l'ADR-0002.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .bom import Bom
from .scenario import CalculationInput

MINUTES_PER_HOUR = Decimal(60)

#: Échelle des montants (ADR-0011). Une division par soixante produit vingt-huit
#: chiffres significatifs, dont vingt-deux que la donnée ne contient pas. On
#: ramène donc le coût de main-d'œuvre à l'échelle réelle là où il naît — une
#: fois, et jamais ensuite : les contributions se somment alors exactement.
SCALE = Decimal("0.000001")


@dataclass(frozen=True)
class PartLine:
    """Une ligne de la vue agrégée : une pièce, pas une occurrence.

    `own_contribution` est la seule grandeur qui se somme : additionner les
    `full_unit_cost` reviendrait à compter chaque ensemble puis son contenu.
    """

    part_ref: str
    cumulative_quantity: Decimal
    occurrence_count: int
    own_unit_cost: Decimal | None
    own_contribution: Decimal | None
    full_unit_cost: Decimal | None


@dataclass(frozen=True)
class CalculationResult:
    lines: tuple[PartLine, ...]
    total_cost: Decimal
    parts_without_price: tuple[str, ...]
    path_own_unit_costs: dict[str, Decimal | None]
    path_full_unit_costs: dict[str, Decimal | None]
    part_own_unit_costs: dict[str, Decimal | None]
    part_full_unit_costs: dict[str, Decimal | None]

    def line(self, part_ref: str) -> PartLine:
        for line in self.lines:
            if line.part_ref == part_ref:
                return line
        raise KeyError(part_ref)

    @property
    def is_incomplete(self) -> bool:
        """Il manque au moins un prix. Le total n'est pas un total fiable."""
        return bool(self.parts_without_price)


def compute(inputs: CalculationInput) -> CalculationResult:
    bom = inputs.bom
    order = bom.topological_order()

    cumulative, occurrences = _quantities(bom, order)
    base_own_unit_cost, missing = _own_unit_costs(inputs)
    base_full_unit_cost = _roll_up(bom, order, base_own_unit_cost)
    path_own, path_full = _path_costs(
        inputs, base_own_unit_cost, base_full_unit_cost
    )
    adjustments = _path_adjustments(inputs, base_own_unit_cost)
    own_unit_cost = _average_path_overrides(
        cumulative, base_own_unit_cost, adjustments
    )
    full_unit_cost = _roll_up(bom, order, own_unit_cost)

    contributions: dict[str, Decimal | None] = {}
    total = Decimal(0)
    for ref in order:
        base_own = base_own_unit_cost[ref]
        contribution = (
            None
            if base_own is None
            else cumulative[ref] * base_own + adjustments.get(ref, Decimal(0))
        )
        contributions[ref] = contribution
        if contribution is not None:
            total += contribution

    # Les moyennes pondérées arrondies peuvent écarter la racine du total de
    # quelques millionièmes : le total exact fait foi. Seulement s'il est
    # complet — un total partiel n'est pas le coût du véhicule.
    if full_unit_cost[bom.root_ref] is not None:
        full_unit_cost[bom.root_ref] = total
    lines = tuple(
        PartLine(
            part_ref=ref,
            cumulative_quantity=cumulative[ref],
            occurrence_count=occurrences[ref],
            own_unit_cost=own_unit_cost[ref],
            own_contribution=contributions[ref],
            full_unit_cost=full_unit_cost[ref],
        )
        for ref in order
    )
    return CalculationResult(
        lines=lines,
        total_cost=total,
        parts_without_price=tuple(missing),
        path_own_unit_costs=path_own,
        path_full_unit_costs=path_full,
        part_own_unit_costs=base_own_unit_cost,
        part_full_unit_costs=base_full_unit_cost,
    )


def _quantities(
    bom: Bom, order: tuple[str, ...]
) -> tuple[dict[str, Decimal], dict[str, int]]:
    """Ce qu'il faut de chaque pièce pour UN véhicule, et en combien d'endroits.

    Une pièce partagée reçoit la somme des apports de tous ses parents : c'est
    ce qui distingue un graphe d'un arbre.
    """
    cumulative = {ref: Decimal(0) for ref in bom.parts}
    occurrences = {ref: 0 for ref in bom.parts}
    cumulative[bom.root_ref] = Decimal(1)
    occurrences[bom.root_ref] = 1

    for ref in order:
        if occurrences[ref] == 0:
            continue
        for child_ref, quantity in bom.children_of(ref):
            cumulative[child_ref] += cumulative[ref] * quantity
            occurrences[child_ref] += occurrences[ref]

    return cumulative, occurrences


def _own_unit_costs(
    inputs: CalculationInput,
) -> tuple[dict[str, Decimal | None], list[str]]:
    """Le coût PROPRE d'une unité : le prix d'achat, ou la seule main-d'œuvre.

    Sur une pièce achetée on ne somme jamais les enfants — elle n'en a pas.
    Sur un ensemble fabriqué on ne cherche jamais de prix : un prix qui
    traînerait dans le catalogue resterait sans effet (ADR-0008).
    """
    prices = inputs.unit_prices
    labour_is_active = "labour" in inputs.active_rules

    costs: dict[str, Decimal | None] = {}
    missing: list[str] = []

    for ref, part in inputs.bom.parts.items():
        if part.is_purchased:
            if ref in prices:
                costs[ref] = prices[ref]
            else:
                costs[ref] = None
                missing.append(ref)
        elif labour_is_active and (
            minutes := inputs.labour_minutes_by_part.get(ref, part.labour_minutes)
        ) is not None:
            costs[ref] = (
                minutes / MINUTES_PER_HOUR * inputs.labour_rate
            ).quantize(SCALE, rounding=ROUND_HALF_UP)
        else:
            costs[ref] = Decimal(0)

    return costs, sorted(missing)


def _average_path_overrides(
    cumulative: dict[str, Decimal],
    base: dict[str, Decimal | None],
    adjustments: dict[str, Decimal],
) -> dict[str, Decimal | None]:
    """Ramène les rares surcharges de chemin dans la vue agrégée.

    Une ligne agrégée ne peut porter qu'un coût unitaire. Quand deux occurrences
    ont des coûts différents, ce coût devient une moyenne pondérée à l'échelle
    de stockage ; la contribution reste la somme exacte des occurrences.
    """
    averaged = dict(base)
    for ref, adjustment in adjustments.items():
        quantity = cumulative[ref]
        if quantity:
            averaged[ref] = (base[ref] + adjustment / quantity).quantize(
                SCALE, rounding=ROUND_HALF_UP
            )
    return averaged


def _path_adjustments(
    inputs: CalculationInput, base: dict[str, Decimal | None]
) -> dict[str, Decimal]:
    adjustments: dict[str, Decimal] = {}
    for path, cost in _path_own_overrides(inputs).items():
        ref = path.rsplit("/", 1)[-1]
        baseline = base[ref]
        if baseline is None:
            continue
        adjustments[ref] = adjustments.get(ref, Decimal(0)) + (
            _path_quantity(inputs.bom, path) * (cost - baseline)
        )
    return adjustments


def _path_own_overrides(inputs: CalculationInput) -> dict[str, Decimal]:
    overrides = dict(inputs.unit_prices_by_path)
    if "labour" not in inputs.active_rules:
        return overrides
    for path, minutes in inputs.labour_minutes_by_path.items():
        overrides[path] = (
            minutes / MINUTES_PER_HOUR * inputs.labour_rate
        ).quantize(SCALE, rounding=ROUND_HALF_UP)
    return overrides


def _path_costs(
    inputs: CalculationInput,
    base_own: dict[str, Decimal | None],
    base_full: dict[str, Decimal | None],
) -> tuple[dict[str, Decimal | None], dict[str, Decimal | None]]:
    """Évalue uniquement les contextes touchés par une surcharge de chemin.

    Les préfixes des chemins surchargés sont les seuls contextes dont le coût
    complet diffère. Sans surcharge, ces dictionnaires restent vides et le
    moteur garde exactement une évaluation par pièce.
    """
    overrides = _path_own_overrides(inputs)
    if not overrides:
        return {}, {}

    affected: set[str] = set()
    for path in overrides:
        refs = path.split("/")
        affected.update("/".join(refs[:index]) for index in range(1, len(refs) + 1))

    own_by_path: dict[str, Decimal | None] = {}
    full_by_path: dict[str, Decimal | None] = {}

    def contextual(path: str) -> Decimal | None:
        if path in full_by_path:
            return full_by_path[path]
        ref = path.rsplit("/", 1)[-1]
        own = overrides.get(path, base_own[ref])
        own_by_path[path] = own
        if own is None:
            full_by_path[path] = None
            return None
        total: Decimal | None = own
        # Tous les enfants touchés sont évalués, même après un coût inconnu :
        # s'arrêter au premier manque ferait disparaître les surcharges des
        # branches voisines, précisément sur un calcul incomplet.
        for child_ref, quantity in inputs.bom.children_of(ref):
            child_path = f"{path}/{child_ref}"
            child_cost = (
                contextual(child_path)
                if child_path in affected
                else base_full[child_ref]
            )
            if child_cost is None or total is None:
                total = None
            else:
                total += quantity * child_cost
        full_by_path[path] = total
        return total

    contextual(inputs.bom.root_ref)
    return own_by_path, full_by_path


def _path_quantity(bom: Bom, path: str) -> Decimal:
    refs = path.split("/")
    quantity = Decimal(1)
    for parent_ref, child_ref in zip(refs, refs[1:]):
        quantity *= next(
            edge_quantity
            for candidate, edge_quantity in bom.children_of(parent_ref)
            if candidate == child_ref
        )
    return quantity


def _roll_up(
    bom: Bom, order: tuple[str, ...], own_unit_cost: dict[str, Decimal | None]
) -> dict[str, Decimal | None]:
    """Le coût unitaire COMPLET : le propre, plus celui des enfants.

    C'est ce qu'on affiche sur une ligne de l'arbre ; il ne se somme pas entre
    niveaux. Un enfant sans prix rend son parent incalculable plutôt que
    faussement bon marché.
    """
    rolled: dict[str, Decimal | None] = {}
    for ref in reversed(order):
        own = own_unit_cost[ref]
        if own is None:
            rolled[ref] = None
            continue
        total = own
        for child_ref, quantity in bom.children_of(ref):
            child_cost = rolled[child_ref]
            if child_cost is None:
                total = None
                break
            total += quantity * child_cost
        rolled[ref] = total
    return rolled
