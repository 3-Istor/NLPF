"""Client de l'API de prix.

Tout ce qui peut mal tourner ici — timeout, port fermé, JSON illisible — sort
sous la forme d'une erreur du port `PriceSource`. L'application ne voit jamais
passer une exception d'`urllib` : elle ne saurait pas quoi en faire, et le mode
de panne P1 deviendrait un plantage.

`urllib` plutôt qu'un client tiers : un appel synchrone avec un délai, c'est
tout ce dont cette tranche a besoin.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Sequence
from urllib.parse import urlencode

from ..application.ports import (
    PriceHistory,
    PriceNotQuoted,
    PricePoint,
    PriceSourceError,
    PriceSourceTimeout,
    Quote,
)


class HttpPriceSource:
    name = "price-api"

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 2.0,
        failure_mode: str = "none",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        #: Sert à provoquer une panne en démonstration et en test. En dehors de
        #: « none », c'est un mode d'essai, pas un réglage de production.
        self.failure_mode = failure_mode

    def fetch(self, refs: Sequence[str], currency: str) -> Sequence[Quote]:
        query = urlencode({"refs": ",".join(refs), "currency": currency})
        try:
            return _to_quotes(self._get(f"/prices?{query}"))
        except urllib.error.HTTPError as refused:
            raise PriceSourceError(f"la source de prix a refusé ({refused.code})") from refused

    def history(self, ref: str, currency: str) -> PriceHistory:
        query = urlencode({"ref": ref, "currency": currency})
        try:
            payload = self._get(f"/history?{query}")
        except urllib.error.HTTPError as refused:
            if refused.code == 404:
                raise PriceNotQuoted(f"{ref} n'est pas coté en {currency}") from refused
            raise PriceSourceError(f"historique refusé ({refused.code})") from refused
        return _to_history(payload)

    def _get(self, path: str) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"X-Mock-Failure": self.failure_mode},
        )

        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (socket.timeout, TimeoutError) as failure:
            raise PriceSourceTimeout(
                f"aucune réponse en {self.timeout_seconds} s"
            ) from failure
        except urllib.error.HTTPError:
            # Une réponse, même un refus : à l'appelant de dire ce qu'elle vaut.
            raise
        except urllib.error.URLError as failure:
            # Port fermé, DNS, connexion refusée : du point de vue de
            # l'application, c'est la même chose qu'un silence.
            raise PriceSourceTimeout(
                f"source de prix injoignable ({failure.reason})"
            ) from failure
        except json.JSONDecodeError as failure:
            raise PriceSourceError(
                f"réponse illisible de la source de prix : {failure}"
            ) from failure

        return payload


def _to_history(payload: dict) -> PriceHistory:
    """Comme une cotation : ramenée à l'unité, `per` divisé une fois, ici."""
    try:
        per = Decimal(str(payload.get("per", 1)))
        if per <= 0:
            raise PriceSourceError(f"quantité de référence {per}")
        unit = lambda value: Decimal(str(value)) / per  # noqa: E731
        return PriceHistory(
            part_ref=payload["ref"],
            currency=payload["currency"],
            unit=payload.get("unit", ""),
            reference=unit(payload["reference"]),
            points=tuple(
                PricePoint(day=point["date"], price=unit(point["price"]))
                for point in payload["points"]
            ),
            now_at=payload["now"]["at"],
            now_price=unit(payload["now"]["price"]),
            profile=payload.get("profile"),
            drivers={
                name: Decimal(str(weight))
                for name, weight in (payload.get("drivers") or {}).items()
            },
            origin_currency=payload.get("origin_currency"),
        )
    except (KeyError, TypeError, InvalidOperation) as unreadable:
        raise PriceSourceError(f"historique illisible : {unreadable}") from unreadable


def _to_quotes(payload: dict) -> list[Quote]:
    """Ramène chaque prix à l'unité, sans juger de sa vraisemblance.

    Ce qui est illisible ressort en cotation sans prix, avec ce que l'API a
    répondu : décider si une valeur est aberrante appartient à l'application,
    qui seule connaît le dernier prix connu.

    Le catalogue cote la visserie par cent : ignorer `per` multiplierait par
    cent le coût de toute la visserie du véhicule, sans lever la moindre erreur.
    """
    quotes: list[Quote] = []
    for raw in payload.get("prices", []):
        ref = raw.get("ref")
        if ref is None:
            continue
        try:
            amount = Decimal(str(raw["price"]))
            per = Decimal(str(raw.get("per", 1)))
        except (InvalidOperation, KeyError, TypeError):
            quotes.append(
                Quote(ref, None, str(raw.get("price")), "valeur non numérique")
            )
            continue
        if per <= 0:
            quotes.append(
                Quote(ref, None, str(raw.get("price")), f"quantité de référence {per}")
            )
            continue
        quotes.append(Quote(ref, amount / per, str(raw["price"])))
    return quotes
