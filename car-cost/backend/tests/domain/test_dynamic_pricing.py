"""Prix et stock SAV : exemples indépendants du réseau et du fichier fourni."""
from decimal import Decimal as D

from carcost.domain.dynamic_pricing import Component, current_price, production_quantities


def component(warranty=False):
    return Component('P', 'Câble', D('10.25'), D('2.5'), warranty,
                     {'cuivre': D('0.6'), 'energie': D('0.4')})


def test_price_changes_and_base_is_preserved():
    part = component()
    assert current_price(part, {'cuivre': D('0'), 'energie': D('0')}) == D('10.25')
    assert current_price(part, {'cuivre': D('0.1'), 'energie': D('-0.05')}) == D('10.66')
    assert part.base_price == D('10.25')


def test_line_cost_is_price_times_quantity():
    part = component()
    price = current_price(part, {'cuivre': D('0.1'), 'energie': D('-0.05')})
    assert price * part.quantity == D('26.650')


def test_warranty_adds_stock_rounded_up_without_changing_unit_price():
    part = component(True)
    assert production_quantities(part, 100) == (D('250'), D('258'))
    assert part.base_price == D('10.25')


def test_no_warranty_preserves_fractional_quantity():
    assert production_quantities(component(), 3) == (D('7.5'), D('7.5'))
