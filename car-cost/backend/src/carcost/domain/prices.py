"""Le snapshot de prix : une photographie datée et immuable (ADR-0003).

Le domaine sait qu'un prix a une date et qu'il vieillit. Il ne sait pas qu'il
existe une API, ni qu'elle tombe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Mapping

# Au-delà, un snapshot est marqué périmé. Valeur métier jamais fournie
# (ambiguïté A6 du cadrage) : hypothèse de travail, paramétrable, et affichée.
FRESHNESS_LIMIT = timedelta(hours=24)


class SnapshotStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    #: Au moins un prix vient d'un repli ligne à ligne, ou manque. Un snapshot
    #: entièrement issu d'un repli n'existe pas : en cas de panne totale on
    #: réutilise le précédent tel quel, sans en fabriquer un daté d'aujourd'hui
    #: avec les prix d'hier.
    DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class PriceSnapshot:
    id: str
    taken_at: datetime
    currency: str
    source: str
    prices: Mapping[str, Decimal]
    #: Pièces dont le prix vient du snapshot précédent : valeur refusée, ou
    #: absente de la réponse.
    fallback_refs: frozenset[str] = field(default_factory=frozenset)
    #: Pièces sans aucun prix, ni frais ni ancien. Elles sont nommées, jamais
    #: remplacées par zéro.
    missing_refs: frozenset[str] = field(default_factory=frozenset)
    #: Parmi les précédentes, celles dont la valeur reçue a été refusée plutôt
    #: qu'absente. La différence se lit sur la ligne : une valeur refusée
    #: renvoie au journal de quarantaine, une absence renvoie à la source.
    quarantined_refs: frozenset[str] = field(default_factory=frozenset)
    #: La nomenclature pour laquelle les prix ont été demandés. None pour un
    #: snapshot antérieur à la coexistence de plusieurs nomenclatures.
    bom_version: str | None = None

    def age(self, now: datetime) -> timedelta:
        return now - self.taken_at

    def status(self, now: datetime) -> SnapshotStatus:
        if self.fallback_refs or self.missing_refs:
            return SnapshotStatus.DEGRADED
        if self.age(now) > FRESHNESS_LIMIT:
            return SnapshotStatus.STALE
        return SnapshotStatus.FRESH
