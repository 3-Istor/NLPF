"""Une horloge injectable et des calculs en RAM, évalués à la demande."""
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from decimal import Decimal
import time
from types import MappingProxyType
from typing import Callable, Mapping

from ..domain.dynamic_pricing import PricingBom, component_rows, current_prices

SECONDS_YEAR = 365 * 24 * 60 * 60
SIM_DURATION = 40 * 60
SPEED = SECONDS_YEAR / SIM_DURATION


@dataclass(frozen=True)
class PriceSnapshot:
    day: int
    date: datetime
    indices: Mapping[str, Decimal]
    variations: Mapping[str, Decimal]


class PriceSimulation:
    def __init__(self, models: Mapping[str, PricingBom],
                 history: Mapping[str, tuple[Decimal, ...]], *,
                 start_date: date = date(2026, 1, 1),
                 clock: Callable[[], float] = time.time):
        self.models = MappingProxyType(dict(models))
        self.history = history
        self.start_date = start_date
        self.clock = clock
        self.start_time = clock()

    def snapshot(self) -> PriceSnapshot:
        elapsed = max(Decimal(0), Decimal(str(self.clock())) - Decimal(str(self.start_time)))
        simulated_seconds = (elapsed * Decimal(str(SPEED))) % SECONDS_YEAR
        position = simulated_seconds / (24 * 60 * 60)
        day = int(position)
        progression = position - day
        next_day = (day + 1) % 365
        indices = {name: values[day] + progression * (values[next_day] - values[day])
                   for name, values in self.history.items()}
        variations = {name: value / self.history[name][0] - 1
                      for name, value in indices.items()}
        simulated_date = datetime.combine(self.start_date, datetime_time(), timezone.utc)
        simulated_date += timedelta(seconds=float(simulated_seconds))
        return PriceSnapshot(day, simulated_date,
                             MappingProxyType(indices), MappingProxyType(variations))

    def quote(self, model: str) -> dict:
        snapshot = self.snapshot()
        bom = self.models[model]
        document = _copy_json(bom.document)
        for row in component_rows(document['categories']):
            prices = current_prices(bom.components[row['id']], snapshot.variations)
            row['prix_unitaire']['prix'] = prices.unit_price
            row['prix_unitaire']['prix_eur'] = prices.unit_price_eur
            row['prix_final']['prix'] = prices.final_price
            row['prix_final']['prix_eur'] = prices.final_price_eur
        return document


def _copy_json(value):
    # Les mappings et tuples figés ne supportent pas deepcopy ; chaque réponse
    # reconstruit ses conteneurs sans partager de référence mutable avec la base.
    if isinstance(value, Mapping):
        return {key: _copy_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_copy_json(child) for child in value]
    return value
