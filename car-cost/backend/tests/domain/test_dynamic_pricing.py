"""Prix de base immuables et quantités totales imposées par la BOM."""
from decimal import Decimal as D

from carcost.domain.dynamic_pricing import Component, current_prices


def component(total='5'):
    return Component('P', D('100'), D('120'), D(total),
                     {'cuivre': D('0.6'), 'energie': D('0.4')})


def test_both_currencies_and_totals_use_the_same_factor():
    part = component()
    result = current_prices(part, {'cuivre': D('0.1'), 'energie': D('0.05')})
    assert result.unit_price == D('108')
    assert result.unit_price_eur == D('129.6')
    assert result.final_price == D('540')
    assert result.final_price_eur == D('648')
    assert part.base_price == D('100')
    assert part.base_price_eur == D('120')


def test_supplied_total_is_used_without_percentage_or_ceiling():
    result = current_prices(component('6.25'), {'cuivre': D(0), 'energie': D(0)})
    assert result.final_price == D('625')
    assert result.final_price_eur == D('750')


def test_calculations_do_not_round_money():
    result = current_prices(component('3'), {'cuivre': D('0.0001'), 'energie': D(0)})
    assert result.unit_price == D('100.006')
    assert result.final_price == D('300.018')
