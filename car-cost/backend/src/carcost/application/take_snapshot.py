"""Prendre un snapshot de prix, et savoir quoi faire quand l'API déraille.

Trois pannes, trois réactions, et aucune n'est silencieuse.

**L'API se tait** (P1) — le dernier snapshot valide reste en vigueur, tel quel.
On n'en fabrique pas un daté d'aujourd'hui avec les prix d'hier : ce serait
faire passer des prix anciens pour des prix frais, exactement ce que
l'affichage de l'âge existe pour empêcher.

**L'API répond une aberration** (P2) — la valeur est mise en quarantaine, avec
ce qu'elle valait et pourquoi elle a été refusée. On retombe sur la dernière
valeur saine de cette pièce. Le snapshot est marqué dégradé.

**L'API ne répond rien pour une pièce** (P3) — même repli. S'il n'existe aucun
historique, la pièce est **nommée** : pas de zéro, pas d'interpolation, pas le
prix d'une pièce voisine. Le calcul qui la rencontrera sera incomplet.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence
from zoneinfo import ZoneInfo

from ..domain.prices import PriceSnapshot
from .ports import PriceSource, PriceSourceError, Quote

#: Au-delà de cet écart au dernier prix connu, on tient la valeur pour une
#: erreur de source plutôt que pour une variation. Hypothèse de travail
#: (ambiguïté A5 du cadrage) : un seuil trop serré met tout en quarantaine et
#: l'outil paraît cassé ; trop lâche, il avale n'importe quoi.
DEVIATION_LIMIT = Decimal("0.5")


#: L'heure lue dans l'identifiant est celle des utilisateurs, pas celle du serveur.
SNAPSHOT_ID_ZONE = ZoneInfo("Europe/Paris")


def new_snapshot_id(now: datetime) -> str:
    """`snp-2026-10-06-1923-a1b2c3` : la minute de la prise se lit dans la liste ;
    le suffixe aléatoire départage deux prises dans la même minute."""
    return f"snp-{now.astimezone(SNAPSHOT_ID_ZONE):%Y-%m-%d-%H%M}-{uuid.uuid4().hex[:6]}"


class NoPriceAvailable(Exception):
    """Aucun prix, ni frais ni ancien. Un total ne peut pas être produit."""


@dataclass(frozen=True)
class QuarantinedPrice:
    part_ref: str
    rejected_value: str
    reason: str
    #: Ce qu'on a utilisé à la place, ou None s'il n'y avait rien.
    replacement: Decimal | None


@dataclass(frozen=True)
class SnapshotTaken:
    snapshot: PriceSnapshot
    quarantined: tuple[QuarantinedPrice, ...] = ()
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class TookFallback:
    """Le snapshot d'avant, réutilisé tel quel — pas une copie datée de ce jour."""

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
    bom_version: str | None = None,
) -> SnapshotTaken | TookFallback:
    try:
        quotes = {quote.part_ref: quote for quote in source.fetch(refs, currency)}
    except PriceSourceError as failure:
        # Un seul appel : on ne réessaie pas en boucle devant un utilisateur
        # qui attend. Le repli est le comportement normal, pas un cas d'erreur.
        if previous is None:
            raise NoPriceAvailable(
                f"la source de prix n'a pas répondu ({failure}) et aucun "
                f"snapshot antérieur n'existe"
            ) from failure
        return TookFallback(snapshot=previous, reason=str(failure))

    prices: dict[str, Decimal] = {}
    quarantined: list[QuarantinedPrice] = []
    fallback: list[str] = []
    missing: list[str] = []

    for ref in refs:
        known = previous.prices.get(ref) if previous else None
        quote = quotes.get(ref)

        if quote is None:
            _fall_back(ref, known, prices, fallback, missing)
            continue

        refusal = _why_refused(quote, known)
        if refusal is None:
            assert quote.price is not None
            prices[ref] = quote.price
            continue

        quarantined.append(
            QuarantinedPrice(
                part_ref=ref,
                rejected_value=quote.raw,
                reason=refusal,
                replacement=known,
            )
        )
        _fall_back(ref, known, prices, fallback, missing)

    return SnapshotTaken(
        snapshot=PriceSnapshot(
            id=snapshot_id,
            taken_at=now,
            currency=currency,
            source=getattr(source, "name", "price-api"),
            prices=prices,
            fallback_refs=frozenset(fallback),
            missing_refs=frozenset(missing),
            quarantined_refs=frozenset(entry.part_ref for entry in quarantined),
            bom_version=bom_version,
        ),
        quarantined=tuple(quarantined),
        missing=tuple(sorted(missing)),
    )


def purchased_refs(bom) -> list[str]:
    """Les pièces dont on demande le prix : les achetées, et elles seules.
    Un ensemble fabriqué n'a pas de prix (ADR-0008)."""
    return sorted(ref for ref, part in bom.parts.items() if part.is_purchased)


def snapshot_for_bom(
    source: PriceSource,
    bom,
    *,
    bom_version: str,
    currency: str,
    previous: PriceSnapshot | None,
    now: datetime,
    snapshot_id: str,
) -> SnapshotTaken | TookFallback:
    """Les prix de toutes les pièces achetées d'une nomenclature.

    Le même chemin sert la ligne de commande, le démarrage, le bouton
    « Figer les prix » et le mode direct : un seul endroit décide de ce qui
    est quarantaine, repli ou manque.
    """
    return take_snapshot(
        source,
        refs=purchased_refs(bom),
        currency=currency,
        previous=previous,
        now=now,
        snapshot_id=snapshot_id,
        bom_version=bom_version,
    )


def _fall_back(
    ref: str,
    known: Decimal | None,
    prices: dict[str, Decimal],
    fallback: list[str],
    missing: list[str],
) -> None:
    if known is None:
        missing.append(ref)
        return
    prices[ref] = known
    fallback.append(ref)


def _why_refused(quote: Quote, known: Decimal | None) -> str | None:
    """La valeur est-elle exploitable ? Si non, en une phrase lisible.

    Le message part dans le journal de quarantaine et jusqu'à l'écran : « refusé »
    sans raison oblige l'utilisateur à nous croire sur parole.
    """
    if quote.price is None:
        return quote.reason or "réponse inexploitable"
    if quote.price < 0:
        return "prix négatif"
    if quote.price == 0:
        return "prix nul sur une pièce achetée"
    if known is not None and known > 0:
        deviation = abs(quote.price - known) / known
        if deviation > DEVIATION_LIMIT:
            return (
                f"écart de {(deviation * 100).quantize(Decimal('1'))} % au dernier "
                f"prix connu ({known})"
            )
    return None
