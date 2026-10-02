"""Profils synthétiques validés ; le libellé prime sur la description."""
from decimal import Decimal
import re
import unicodedata


# L'ordre des indices est commun aux profils pour rendre les poids comparables.
INDEX_NAMES = ('cuivre', 'aluminium', 'acier', 'lithium', 'nickel',
               'semi_conducteurs', 'energie', 'transport', 'GBP_EUR')
PROFILE_WEIGHTS = {
    'cable':       ('0.55', '0', '0', '0', '0', '0', '0.15', '0.10', '0.20'),
    'aluminium':   ('0', '0.50', '0', '0', '0', '0', '0.20', '0.10', '0.20'),
    'steel':       ('0', '0', '0.50', '0', '0', '0', '0.20', '0.10', '0.20'),
    'battery':     ('0.10', '0.10', '0', '0.25', '0.20', '0.15', '0.05', '0.05', '0.10'),
    'electronics': ('0.10', '0', '0', '0', '0', '0.55', '0.10', '0.10', '0.15'),
    'motor':       ('0.25', '0.15', '0.10', '0', '0', '0.25', '0.10', '0.05', '0.10'),
    'rubber':      ('0', '0', '0.10', '0', '0', '0', '0.50', '0.20', '0.20'),
    'composite':   ('0', '0.10', '0', '0', '0', '0', '0.45', '0.15', '0.30'),
    'default':     ('0', '0', '0.20', '0', '0', '0', '0.35', '0.20', '0.25'),
}

# Une fixation reste une fixation, même si elle mentionne l'organe qu'elle fixe.
RULES = tuple((profile, re.compile(pattern)) for profile, pattern in (
    ('steel', r'\b(?:vis|visserie|boulons?|ecrous?|rondelles?|goujons?|rivets?|colliers?|agrafes?)\b'),
    ('cable', r'\b(?:cables?|faisceaux?|wiring|harness)\b'),
    ('electronics', r'\b(?:ecu|tcu|vcu|bcm|bms|adas|capteurs?|sensors?|electronique|radars?|cameras?|calculateurs?|tpms)\b'),
    ('motor', r'\b(?:moteurs? electriques?|electric motors?|emotor|inverters?|onduleurs?)\b'),
    ('aluminium', r'\b(?:aluminium|aluminum|jantes?)\b'),
    ('steel', r'\b(?:acier|steel|chassis|sous cadres?|supports?|berceaux?|triangles?|biellettes?|bras de suspension)\b'),
    ('battery', r'\b(?:batterie hv|pack hv|(?:pack|modules?|cellules?) (?:de )?batterie)\b'),
    ('rubber', r'\b(?:pneus?|pneumatiques?|caoutchouc|rubber|tires?|tyres?)\b'),
    ('composite', r'\b(?:carbone|carbon|composites?|carrosserie|monocoque|ailes?|capot|pare chocs|portes?)\b'),
))


def _normalize(text: str) -> str:
    text = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def classify_drivers(name: str, description: str, currency: str) -> dict[str, Decimal]:
    if currency not in ('GBP', 'EUR'):
        raise ValueError(f'devise sans indice de change : {currency}')
    profile = 'default'
    for text in (name, description):
        normalized = _normalize(text)
        match = next((key for key, pattern in RULES if pattern.search(normalized)), None)
        if match:
            profile = match
            break
    weights = {key: Decimal(value) for key, value in
               zip(INDEX_NAMES, PROFILE_WEIGHTS[profile]) if Decimal(value)}
    if currency == 'EUR':
        remaining = 1 - weights['GBP_EUR']
        weights = {key: value / remaining for key, value in weights.items()
                   if key != 'GBP_EUR'}
        # Une division périodique en Decimal laisse parfois un résidu : la
        # dernière composante garantit une somme exactement égale à un.
        last = next(reversed(weights))
        weights[last] = 1 - sum(value for key, value in weights.items() if key != last)
        weights['GBP_EUR'] = Decimal(0)
    return weights
