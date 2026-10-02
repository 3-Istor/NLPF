"""Pondérations demandées, classement par libellé et exposition au change."""
from decimal import Decimal as D

import pytest

from carcost.domain.price_drivers import classify_drivers


@pytest.mark.parametrize('name,driver,weight', [
    ('Faisceau haute tension', 'cuivre', '0.55'),
    ('Jante avant', 'aluminium', '0.50'),
    ('Vis M6', 'acier', '0.50'),
    ('Batterie HV', 'lithium', '0.25'),
    ('Capteur de pression', 'semi_conducteurs', '0.55'),
    ('Moteur électrique avant', 'cuivre', '0.25'),
    ('Inverter arrière', 'semi_conducteurs', '0.25'),
    ('Pneu avant', 'energie', '0.50'),
    ('Panneau carrosserie carbone', 'energie', '0.45'),
    ('Pièce inconnue', 'energie', '0.35'),
])
def test_profiles_and_eur_normalization(name, driver, weight):
    gbp = classify_drivers(name, '', 'GBP')
    eur = classify_drivers(name, '', 'EUR')
    assert gbp[driver] == D(weight)
    assert sum(gbp.values()) == sum(eur.values()) == 1
    assert eur['GBP_EUR'] == 0
    assert eur[driver] == pytest.approx(gbp[driver] / (1 - gbp['GBP_EUR']))


def test_name_has_priority_over_description():
    assert classify_drivers('Capteur batterie HV', 'Cuivre aluminium', 'GBP')[
        'semi_conducteurs'] == D('0.55')
    assert classify_drivers('Vis de châssis', 'Fixation faisceau', 'GBP')['acier'] == D('0.50')


def test_description_is_used_when_name_is_unknown():
    assert classify_drivers('Pièce spécifique', 'Aluminium forgé', 'GBP')['aluminium'] == D('0.50')


def test_partial_words_do_not_classify_as_screws():
    assert classify_drivers('Pare-brise', 'Visibilité améliorée', 'GBP')['GBP_EUR'] == D('0.25')


@pytest.mark.parametrize('name,driver,weight', [
    ('Démarreur 12 V V8', 'cuivre', '0.25'),
    ('Alternateur 12 V', 'cuivre', '0.25'),
    ('Réducteur arrière gauche', 'acier', '0.50'),
    ('Pignon intermédiaire marche arrière', 'acier', '0.50'),
    ("Train d'engrenages marche arrière", 'acier', '0.50'),
    ('Chargeur embarqué 22 kW', 'semi_conducteurs', '0.55'),
    ('Module contacteurs charge rapide DC', 'semi_conducteurs', '0.55'),
    ('Filtre EMI haute tension', 'semi_conducteurs', '0.55'),
    ('Pack batterie traction 800 V', 'lithium', '0.25'),
    ('Moteur électrique arrière gauche', 'cuivre', '0.25'),
    ('Huile réducteurs électriques', 'energie', '0.35'),
])
def test_new_variant_components(name, driver, weight):
    assert classify_drivers(name, '', 'GBP')[driver] == D(weight)
