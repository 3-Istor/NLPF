"""Prendre un snapshot de prix, et savoir quoi faire quand l'API ne répond pas.

Trois issues, trois seulement, et aucune n'est silencieuse :

  - `SnapshotTaken`   : l'API a répondu, un nouveau snapshot existe ;
  - `TookFallback`    : l'API n'a pas répondu, le dernier snapshot valide reste
                        en vigueur, et le calcul qui l'utilisera sera marqué
                        dégradé ;
  - `NoPriceAvailable`: l'API n'a pas répondu et il n'y a aucun historique. On
                        refuse plutôt que d'inventer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from ..domain.prices import PriceSnapshot
from .ports import PriceSource, PriceSourceError


class NoPriceAvailable(Exception):
    """Aucun prix, ni frais ni ancien. Un total ne peut pas être produit."""


@dataclass(frozen=True)
class SnapshotTaken:
    snapshot: PriceSnapshot


@dataclass(frozen=True)
class TookFallback:
    """Le snapshot d'avant, réutilisé tel quel — pas une copie datée de ce jour.

    Fabriquer un snapshot du jour avec les prix de la veille ferait passer des
    prix anciens pour des prix frais : c'est exactement ce que l'affichage de
    l'âge doit empêcher.
    """

    snapshot: PriceSnapshot
    reason: str


def take_snapshot(
    source: PriceSource,
    *,
    refs: Sequence[str],
    currency: str,
    previous: PriceSnapshot | None,
    now: datetime,
    snapshot_id: str,
) -> SnapshotTaken | TookFallback:
    try:
        prices = source.fetch(refs, currency)
    except PriceSourceError as failure:
        # Un seul appel : on ne réessaie pas en boucle devant un utilisateur
        # qui attend. Le repli est le comportement normal, pas un cas d'erreur.
        if previous is None:
            raise NoPriceAvailable(
                f"la source de prix n'a pas répondu ({failure}) et aucun "
                f"snapshot antérieur n'existe"
            ) from failure
        return TookFallback(snapshot=previous, reason=str(failure))

    return SnapshotTaken(
        snapshot=PriceSnapshot(
            id=snapshot_id,
            taken_at=now,
            currency=currency,
            source=getattr(source, "name", "price-api"),
            prices=dict(prices),
        )
    )
