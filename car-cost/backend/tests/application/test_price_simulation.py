"""Une seule horloge, sans cumul des variations ni mutation des modèles."""
from decimal import Decimal as D

import pytest

from carcost.application.price_simulation import PriceSimulation, SIM_DURATION
from carcost.infrastructure.price_data import load_boms
from infrastructure.test_price_data import write_models, first_row


@pytest.fixture
def simulation(tmp_path):
    write_models(tmp_path)
    models = load_boms(tmp_path)
    now = [0.0]
    # Tous les indices suivent la même variation pour rendre le calcul indépendant du profil.
    history = {name: tuple(D(100 + day) for day in range(365))
               for name in ('cuivre', 'energie', 'transport', 'GBP_EUR')}
    return PriceSimulation(models, history, clock=lambda: now[0]), now


def test_time_changes_price_and_loops_after_forty_minutes(simulation):
    service, now = simulation
    first = service.quote('hybride')
    now[0] = 1200
    later = service.quote('hybride')
    assert first_row(later)['prix_unitaire']['prix'] == D('282.5')
    now[0] = SIM_DURATION
    assert service.quote('hybride') == first
    now[0] = SIM_DURATION * 20 + SIM_DURATION - 0.01
    assert service.snapshot().day == 364


def test_linear_interpolation_and_continuous_date(simulation):
    service, now = simulation
    now[0] = 1200
    middle = service.snapshot()
    assert middle.day == 182
    assert middle.indices['energie'] == D('282.5')
    assert middle.date.isoformat() == '2026-07-02T12:00:00+00:00'
    now[0] += 0.1
    assert service.snapshot().indices['energie'] > middle.indices['energie']


def test_last_day_interpolates_toward_first_day(simulation):
    service, now = simulation
    now[0] = SIM_DURATION * 364.5 / 365
    assert service.snapshot().indices['energie'] == pytest.approx(D('282'), abs=D('1e-9'))
    now[0] = SIM_DURATION - 1e-8
    assert service.snapshot().indices['energie'] == pytest.approx(D('100'), abs=D('1e-6'))
    now[0] = SIM_DURATION
    assert service.snapshot().indices['energie'] == D('100')


def test_no_compounding_and_response_cannot_mutate_bases(simulation):
    service, now = simulation
    now[0] = 1200
    first = service.quote('hybride')
    expected = first_row(first)['prix_unitaire']['prix']
    for _ in range(5):
        assert service.quote('hybride') == first
    first_row(first)['prix_unitaire']['prix'] = -1
    first_row(first)['quantite_totale'] = -1
    assert first_row(service.quote('hybride'))['prix_unitaire']['prix'] == expected
    assert first_row(service.models['hybride'].document)['prix_unitaire']['prix'] == 100
    now[0] = 0
    assert first_row(service.quote('hybride'))['prix_unitaire']['prix'] == D('100')


def test_clock_is_sampled_once_per_quote(simulation):
    service, _ = simulation
    calls = []
    def clock():
        calls.append(1)
        return 0
    service.clock = clock
    service.quote('hybride')
    assert len(calls) == 1
