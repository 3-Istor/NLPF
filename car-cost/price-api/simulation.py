"""Les prix bougent : une année de marché simulée, rejouée en boucle.

Neuf indices SYNTHÉTIQUES (cuivre, aluminium, acier, lithium, nickel,
semi-conducteurs, énergie, transport, cours GBP→EUR) ont une valeur par jour
sur 365 jours (`data/price_indices.json`, produit par `tools/price_history`).
Une année dure `year_minutes` minutes réelles — 40 par défaut — puis recommence.
Entre deux jours, la valeur est interpolée linéairement, du jour 364 au jour 0
compris : la courbe ne saute pas au bouclage.

Le prix d'une pièce à l'instant t :

    facteur = 1 + Σ poids × (indice(t) / indice(jour 0) − 1) + part propre(t)
    prix    = prix de référence × facteur [× variation du change]

La part propre à la pièce (`wobble`) évite que toutes les pièces d'un même
profil dessinent la même courbe : quelques sinusoïdes de période 1 an, 1/2, 1/3,
1/4, dont amplitudes et phases sont tirées d'une graine dérivée de la référence.
Nulle au jour 0 (le prix part de sa référence) et sans saut au bouclage.

Les bornes du catalogue (`year_min`, `year_max`) tiennent la courbe : la partie
au-dessus de la référence est étirée pour que son sommet atteigne `year_max`,
celle en dessous pour que son creux atteigne `year_min`. Le jour 0 reste à la
référence, la forme propre à la pièce est gardée. Sans bornes, prix brut.

Les poids viennent du catalogue (`drivers`), calculés à la génération du jeu de
données : rien n'est deviné ici. Le change ne s'applique qu'entre GBP et EUR,
selon la devise du fournisseur (`origin_currency`) : un fournisseur britannique
garde son prix en livres, son prix en euros suit le cours du jour.

Le calcul a lieu à la demande, sans tâche de fond : à instant égal, prix égaux.
Bibliothèque standard seule, comme le reste du simulateur.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from datetime import date, datetime, time as day_start, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Callable

SECONDS_PER_DAY = 24 * 60 * 60
DAYS = 365
SCALE = Decimal("0.000001")
FX = "GBP_EUR"
WOBBLE_TERMS = 4
WOBBLE_AMPLITUDE = 0.06  # par terme, divisée par l'harmonique : ±10 % en général


@lru_cache(maxsize=None)
def _wobble_terms(ref: str) -> tuple[tuple[int, float, float], ...]:
    """(harmonique, amplitude, phase) propres à la référence, stables d'un
    lancement à l'autre (sha256, pas `hash()` qui change à chaque processus)."""
    rng = random.Random(hashlib.sha256(ref.encode("utf-8")).digest())
    return tuple(
        (k, rng.uniform(0, WOBBLE_AMPLITUDE) / k, rng.uniform(0, 2 * math.pi))
        for k in range(1, WOBBLE_TERMS + 1)
    )


def _wobble(ref: str, position: float) -> float:
    angle = 2 * math.pi * position / DAYS
    return sum(
        amplitude * (math.sin(k * angle + phase) - math.sin(phase))
        for k, amplitude, phase in _wobble_terms(ref)
    )


def wobble(ref: str, position: Decimal) -> Decimal:
    """La part du facteur propre à la pièce ; nulle sans référence."""
    if not ref:
        return Decimal(0)
    return Decimal(repr(_wobble(ref, float(position))))


class Market:
    """Les indices et l'horloge. Sans `year_minutes`, le marché est figé au
    jour 0 : chaque prix vaut sa référence (ce qu'attendent les tests du
    client HTTP, et une démonstration qui ne veut pas de bruit)."""

    def __init__(
        self,
        indices_path: Path,
        *,
        year_minutes: float | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        document = json.loads(indices_path.read_text(encoding="utf-8"))
        self.start_date = date.fromisoformat(document["start_date"])
        self.indices = {
            name: tuple(Decimal(value) for value in values)
            for name, values in document["indices"].items()
        }
        for name, values in self.indices.items():
            if len(values) != DAYS:
                raise ValueError(f"indice {name} : {len(values)} valeurs, {DAYS} attendues")
        self.year_minutes = year_minutes
        self.clock = clock
        self.started = clock()
        self._ratios = {
            name: tuple(float(value / values[0]) for value in values)
            for name, values in self.indices.items()
        }
        self._raw_ranges: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}

    # ----------------------------------------------------------------- temps

    def position(self) -> Decimal:
        """Le jour simulé de l'instant présent, avec sa fraction (0 ≤ p < 365)."""
        if not self.year_minutes:
            return Decimal(0)
        elapsed = max(Decimal(0), Decimal(str(self.clock())) - Decimal(str(self.started)))
        speed = Decimal(DAYS * SECONDS_PER_DAY) / (Decimal(str(self.year_minutes)) * 60)
        return (elapsed * speed % (DAYS * SECONDS_PER_DAY)) / SECONDS_PER_DAY

    def moment(self, position: Decimal) -> datetime:
        start = datetime.combine(self.start_date, day_start(), timezone.utc)
        return start + timedelta(days=float(position))

    # --------------------------------------------------------------- indices

    def index(self, name: str, position: Decimal) -> Decimal:
        values = self.indices[name]
        day = int(position)
        fraction = position - day
        following = values[(day + 1) % DAYS]
        return values[day] + fraction * (following - values[day])

    def factor(self, drivers: dict[str, str], position: Decimal) -> Decimal:
        return 1 + sum(
            (
                Decimal(weight) * (self.index(name, position) / self.indices[name][0] - 1)
                for name, weight in drivers.items()
            ),
            Decimal(0),
        )

    def fx_change(self, position: Decimal) -> Decimal:
        return self.index(FX, position) / self.indices[FX][0]

    # ------------------------------------------------------------------ prix

    def price(self, entry: dict, currency: str, position: Decimal, ref: str = "") -> Decimal:
        """Le prix catalogue (pour `price_per` unités) à cette position, ramené
        dans les bornes annuelles du catalogue quand il en a."""
        raw = self.raw_price(entry, currency, position, ref)
        quote = entry["prices"][currency]
        if not ref or "year_min" not in quote or "year_max" not in quote:
            return raw
        reference = Decimal(quote["reference"])
        low, high = Decimal(quote["year_min"]), Decimal(quote["year_max"])
        raw_low, raw_high = self._raw_range(entry, currency, ref)
        if raw >= reference:
            span = raw_high - reference
            price = reference + (raw - reference) * (high - reference) / span if span else reference
        else:
            span = reference - raw_low
            price = reference - (reference - raw) * (reference - low) / span if span else reference
        # Entre deux jours, la courbe brute peut dépasser d'un cheveu ses valeurs journalières.
        return min(max(price, low), high).quantize(SCALE)

    def _raw_range(self, entry: dict, currency: str, ref: str) -> tuple[Decimal, Decimal]:
        """Creux et sommet de l'année brute, jour par jour. En flottants, la même
        formule que `raw_price` : dix fois plus rapide (un premier appel sur
        2 000 pièces tient sous le timeout du client), écart effacé à l'arrondi."""
        key = (ref, currency)
        if key not in self._raw_ranges:
            reference = float(entry["prices"][currency]["reference"])
            drivers = [
                (float(weight), self._ratios[name])
                for name, weight in (entry.get("drivers") or {}).items()
            ]
            origin = entry.get("origin_currency")
            fx = self._ratios[FX]
            series = []
            for day in range(DAYS):
                factor = 1 + sum(w * (r[day] - 1) for w, r in drivers) + _wobble(ref, day)
                if origin == "GBP" and currency == "EUR":
                    factor *= fx[day]
                elif origin == "EUR" and currency == "GBP":
                    factor /= fx[day]
                series.append(reference * factor)
            self._raw_ranges[key] = tuple(
                Decimal(repr(value)).quantize(SCALE) for value in (min(series), max(series))
            )
        return self._raw_ranges[key]

    def raw_price(self, entry: dict, currency: str, position: Decimal, ref: str = "") -> Decimal:
        """Le prix tiré des indices et de la part propre, avant les bornes."""
        reference = Decimal(entry["prices"][currency]["reference"])
        factor = self.factor(entry.get("drivers") or {}, position) + wobble(ref, position)
        origin = entry.get("origin_currency")
        if origin == "GBP" and currency == "EUR":
            factor *= self.fx_change(position)
        elif origin == "EUR" and currency == "GBP":
            factor /= self.fx_change(position)
        return (reference * factor).quantize(SCALE)

    def history(self, entry: dict, currency: str, ref: str = "") -> dict:
        """Un point par jour simulé, et l'instant présent."""
        now = self.position()
        return {
            "points": [
                {
                    "date": (self.start_date + timedelta(days=day)).isoformat(),
                    "price": str(self.price(entry, currency, Decimal(day), ref)),
                }
                for day in range(DAYS)
            ],
            "now": {
                "at": self.moment(now).isoformat(),
                "day": str(now.quantize(Decimal("0.001"))),
                "price": str(self.price(entry, currency, now, ref)),
            },
        }
