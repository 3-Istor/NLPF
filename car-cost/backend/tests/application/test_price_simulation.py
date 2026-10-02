"""Le temps est échantillonné une seule fois, sans tâche périodique."""
from decimal import Decimal as D
import pytest

from carcost.application.price_simulation import PriceSimulation, SIM_DURATION
from carcost.domain.dynamic_pricing import Component


def simulation(now):
    return PriceSimulation(
        [Component('P', 'Pièce', D('10'), D('2'), True, {'energie': D('1')})],
        {'energie': tuple(D(100 + day) for day in range(365))},
        clock=lambda: now[0],
    )


def test_time_changes_price_and_loops_after_forty_minutes():
    now = [1000.0]
    service = simulation(now)
    first = service.snapshot()
    now[0] += SIM_DURATION / 365 * 10 + 0.01
    later = service.snapshot()
    assert first.day == 0
    assert later.day == 10
    assert service.price(service.components['P'], later) > D('11')
    now[0] = 1000 + SIM_DURATION
    assert service.snapshot() == first
    now[0] += SIM_DURATION * 20 + SIM_DURATION - 0.01
    assert service.snapshot().day == 364


def test_totals_separate_production_and_stock():
    service = simulation([0])
    snapshot = service.snapshot()
    assert service.vehicle_cost(snapshot) == D('20')
    assert service.production_cost(100, snapshot) == (D('2000'), D('60'), D('2060'))
    assert service.production_cost(0, snapshot) == (D('0'), D('0'), D('0'))


def test_linear_interpolation_and_continuous_date():
    now = [0.0]
    service = simulation(now)
    now[0] = 1200
    middle = service.snapshot()
    assert middle.day == 182
    assert middle.indices['energie'] == D('282.5')
    assert service.price(service.components['P'], middle) == D('28.25')
    assert middle.date.isoformat() == '2026-07-02T12:00:00+00:00'
    now[0] += 0.1
    assert service.snapshot().indices['energie'] > middle.indices['energie']


def test_last_day_interpolates_toward_first_day():
    now = [0.0]
    service = simulation(now)
    now[0] = SIM_DURATION * 364.5 / 365
    assert service.snapshot().indices['energie'] == pytest.approx(D('282'), abs=D('1e-9'))
    now[0] = SIM_DURATION - 1e-8
    assert service.snapshot().indices['energie'] == pytest.approx(D('100'), abs=D('1e-6'))
    now[0] = SIM_DURATION
    assert service.snapshot().indices['energie'] == D('100')


def test_clock_is_sampled_once_per_snapshot():
    calls = []
    def clock():
        calls.append(1)
        return 0
    service = PriceSimulation([], {'energie': (D('100'),) * 365}, clock=clock)
    assert len(calls) == 1
    snapshot = service.snapshot()
    service.production_cost(100, snapshot)
    assert len(calls) == 2
