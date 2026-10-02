"""Une horloge injectable et des calculs en RAM, évalués à la demande."""
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from decimal import Decimal
import time
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from ..domain.dynamic_pricing import Component, current_price, production_quantities

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
    def __init__(self, components: Sequence[Component],
                 history: Mapping[str, tuple[Decimal, ...]], *,
                 start_date: date = date(2026, 1, 1),
                 clock: Callable[[], float] = time.time):
        self.components = MappingProxyType({part.id: part for part in components})
        self.history = history
        self.start_date = start_date
        self.clock = clock
        self.start_time = clock()
        self.base_cost = sum((part.base_price * part.quantity for part in components),
                             Decimal(0))

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

    def price(self, component: Component, snapshot: PriceSnapshot) -> Decimal:
        return current_price(component, snapshot.variations)

    def vehicle_cost(self, snapshot: PriceSnapshot) -> Decimal:
        return sum((self.price(part, snapshot) * part.quantity
                    for part in self.components.values()), Decimal(0))

    def production_cost(self, vehicles: int, snapshot: PriceSnapshot
                        ) -> tuple[Decimal, Decimal, Decimal]:
        production_cost = Decimal(0)
        stock_cost = Decimal(0)
        for part in self.components.values():
            production, purchase = production_quantities(part, vehicles)
            price = self.price(part, snapshot)
            production_cost += production * price
            stock_cost += (purchase - production) * price
        return production_cost, stock_cost, production_cost + stock_cost
