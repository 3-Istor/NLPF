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
from typing import Mapping, Sequence
from urllib.parse import urlencode

from ..application.ports import PriceSourceError, PriceSourceTimeout


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

    def fetch(self, refs: Sequence[str], currency: str) -> Mapping[str, Decimal]:
        query = urlencode({"refs": ",".join(refs), "currency": currency})
        request = urllib.request.Request(
            f"{self.base_url}/prices?{query}",
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

        return _to_unit_prices(payload)


def _to_unit_prices(payload: dict) -> dict[str, Decimal]:
    """Ramène chaque prix à l'unité.

    Le catalogue cote la visserie par cent : ignorer `per` multiplierait par
    cent le coût de toute la visserie du véhicule, sans lever la moindre erreur.
    """
    prices: dict[str, Decimal] = {}
    for quote in payload.get("prices", []):
        try:
            amount = Decimal(str(quote["price"]))
            per = Decimal(str(quote.get("per", 1)))
        except (InvalidOperation, KeyError) as failure:
            raise PriceSourceError(
                f"prix inexploitable pour {quote.get('ref', '?')} : {quote}"
            ) from failure
        if per <= 0:
            raise PriceSourceError(
                f"quantité de référence invalide pour {quote['ref']} : {per}"
            )
        prices[quote["ref"]] = amount / per
    return prices
