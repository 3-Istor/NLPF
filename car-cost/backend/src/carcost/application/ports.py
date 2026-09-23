"""Ce que l'application attend du monde extérieur.

Un port dit ce dont on a besoin, pas comment on l'obtient : le client HTTP, le
fichier de catalogue ou le double de test sont interchangeables, et aucun n'est
nommé ici.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Protocol, Sequence


class PriceSourceError(Exception):
    """L'appel n'a pas abouti. Jamais propagée telle quelle jusqu'à l'écran."""


class PriceSourceTimeout(PriceSourceError):
    """La source n'a pas répondu dans le temps imparti (mode de panne P1)."""


class PriceSource(Protocol):
    def fetch(
        self, refs: Sequence[str], currency: str
    ) -> Mapping[str, Decimal]:  # pragma: no cover - contrat
        ...
