"""La nomenclature : un graphe orienté acyclique, en table d'arêtes (ADR-0001).

Cette couche ne connaît ni base, ni réseau, ni écran. Elle n'importe rien
d'autre que la bibliothèque standard, et un test d'architecture le vérifie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping


class ValuationMode(str, Enum):
    """Exclusif : une pièce est achetée ou fabriquée, jamais les deux (ADR-0008)."""

    PURCHASED = "purchased"
    MANUFACTURED = "manufactured"


@dataclass(frozen=True)
class Part:
    ref: str
    label: str
    system: str
    unit: str
    valuation_mode: ValuationMode
    carbon_factor: Decimal
    labour_minutes: Decimal | None = None
    mass_kg: Decimal | None = None

    @property
    def is_purchased(self) -> bool:
        return self.valuation_mode is ValuationMode.PURCHASED


@dataclass(frozen=True)
class Edge:
    parent_ref: str
    child_ref: str
    quantity: Decimal


@dataclass(frozen=True)
class Bom:
    root_ref: str
    parts: Mapping[str, Part]
    edges: tuple[Edge, ...]
    _children: dict[str, tuple[tuple[str, Decimal], ...]] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        index: dict[str, list[tuple[str, Decimal]]] = {ref: [] for ref in self.parts}
        for edge in self.edges:
            index[edge.parent_ref].append((edge.child_ref, edge.quantity))
        object.__setattr__(
            self, "_children", {ref: tuple(kids) for ref, kids in index.items()}
        )

    def children_of(self, ref: str) -> tuple[tuple[str, Decimal], ...]:
        return self._children[ref]

    def topological_order(self) -> tuple[str, ...]:
        """Parents avant enfants. Lève si le graphe contient un cycle.

        L'acyclicité n'est pas supposée : elle est établie ici, et c'est le seul
        endroit du domaine qui puisse l'affirmer.
        """
        indegree = {ref: 0 for ref in self.parts}
        for edge in self.edges:
            indegree[edge.child_ref] += 1

        ready = sorted(ref for ref, degree in indegree.items() if degree == 0)
        order: list[str] = []
        while ready:
            ref = ready.pop(0)
            order.append(ref)
            for child_ref, _ in self._children[ref]:
                indegree[child_ref] -= 1
                if indegree[child_ref] == 0:
                    ready.append(child_ref)
            ready.sort()

        if len(order) != len(self.parts):
            unreachable = sorted(set(self.parts) - set(order))
            raise ValueError(
                f"cycle dans la nomenclature : {len(unreachable)} pièces ne sont "
                f"jamais atteignables en ordre topologique, par exemple "
                f"{unreachable[:5]}"
            )
        return tuple(order)
