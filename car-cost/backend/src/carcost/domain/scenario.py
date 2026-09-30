"""Les entrées d'un calcul.

Les prix arrivent ici **déjà résolus** : le domaine ne sait pas d'où ils
viennent, ni qu'il existe une API qui tombe. La résolution du prix unitaire —
référence × multiplicateur fournisseur × coefficient d'usine (ADR-0010) — a lieu
dans la couche application, avant l'appel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

from .bom import Bom


@dataclass(frozen=True)
class CalculationInput:
    bom: Bom
    unit_prices: Mapping[str, Decimal]
    labour_rate: Decimal
    active_rules: frozenset[str] = field(default_factory=lambda: frozenset({"labour"}))
    unit_prices_by_path: Mapping[str, Decimal] = field(default_factory=dict)
    #: Temps de main-d'œuvre posés par le scénario. Ils remplacent celui de la
    #: nomenclature, qui reste intact : la version est figée et partagée entre
    #: scénarios (ADR-0013).
    labour_minutes_by_part: Mapping[str, Decimal] = field(default_factory=dict)
    labour_minutes_by_path: Mapping[str, Decimal] = field(default_factory=dict)
