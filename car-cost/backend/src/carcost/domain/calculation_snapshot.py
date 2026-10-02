"""Le snapshot de calcul : un calcul nommé, figé avec ses hypothèses (ADR-0014).

À ne pas confondre avec le snapshot de prix (ADR-0003). Le snapshot de calcul
copie les paramètres appliqués pour se suffire à lui-même ; seul son nom change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from .text_folding import fold

Scope = Literal["part", "path"]


class InvalidSnapshotName(ValueError):
    """Le nom d'un snapshot est obligatoire : il n'y a pas de valeur de repli."""


def snapshot_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise InvalidSnapshotName("Le nom du snapshot est obligatoire.")
    return name


def name_key(name: str) -> str:
    """Clé d'unicité : sans casse ni accents, comme la recherche."""
    return fold(name.strip())


@dataclass(frozen=True)
class FrozenParameter:
    """Copie d'un paramètre de scénario tel qu'il a été appliqué."""

    part_ref: str
    scope: Scope = "part"
    path: str | None = None
    supplier_id: str | None = None
    plant_id: str | None = None
    price_override: Decimal | None = None
    price_override_justification: str | None = None
    labour_minutes: Decimal | None = None
    purchase_currency: str | None = None


@dataclass(frozen=True)
class CalculationSnapshot:
    id: str
    name: str
    bom_version: str
    scenario_id: str
    scenario_name: str
    calculation_id: str
    price_snapshot_id: str
    display_currency: str
    labour_rate: Decimal
    active_rules: frozenset[str]
    parameters: tuple[FrozenParameter, ...]
    created_at: datetime
    #: Le snapshot dont le scénario figé était reparti, recopié au gel.
    derived_from: str | None = None
    #: Le SAV était-il compté ? Sans cette copie, le total figé ne
    #: s'expliquerait plus dès que le scénario vivant bascule le réglage.
    include_after_sales: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", snapshot_name(self.name))
        object.__setattr__(self, "active_rules", frozenset(self.active_rules))
        ordered = sorted(
            self.parameters,
            key=lambda p: (p.part_ref, p.scope, p.path or ""),
        )
        object.__setattr__(self, "parameters", tuple(ordered))

    @property
    def name_key(self) -> str:
        return name_key(self.name)
