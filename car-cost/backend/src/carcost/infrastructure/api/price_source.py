"""Ce que les routes font de l'API de prix, écrit une fois."""

from __future__ import annotations

from ...application.ports import PriceSourceError


def price_source(repositories):
    """L'API de prix câblée, ou un refus nommé : sans elle, ni direct, ni gel
    de prix, ni historique — mais tout le reste de l'application marche."""
    if repositories.prices is None:
        raise PriceSourceError("aucune API de prix n'est configurée")
    return repositories.prices


def previous_for(repositories, bom_version: str, currency: str):
    """Le dernier snapshot de la nomenclature, s'il est dans cette devise.

    Le repli prend le dernier prix connu d'une pièce : un prix en euros ne
    remplace pas un prix en dollars.
    """
    if repositories.snapshots is None:
        return None
    previous = repositories.snapshots.latest(bom_version)
    if previous is None or previous.currency != currency:
        return None
    return previous
