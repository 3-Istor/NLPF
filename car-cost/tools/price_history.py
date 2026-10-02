"""Produit un historique SYNTHÉTIQUE reproductible ; jamais exécuté par l'API.

Depuis car-cost : python -m tools.price_history
Les amplitudes illustrent des marchés plus ou moins volatils, sans donnée réelle.
"""
import json
import math
from pathlib import Path
import random

# L'historique appartient à l'API simulée : c'est elle qui fait varier les prix.
DESTINATION = Path(__file__).resolve().parents[1] / 'price-api/data/price_indices.json'
PROFILES = {
    'cuivre': (100, .12), 'aluminium': (100, .10), 'acier': (100, .08),
    'lithium': (100, .30), 'nickel': (100, .20), 'energie': (100, .18),
    'transport': (100, .09), 'semi_conducteurs': (100, .14),
    'GBP_EUR': (1.17108, .04),
}


def generate():
    rng = random.Random(20261002)
    indices = {}
    for name, (base, amplitude) in PROFILES.items():
        noise = 0.0
        values = [str(base)]
        for day in range(1, 365):
            noise = .92 * noise + rng.uniform(-.025, .025)
            cycle = math.sin(2 * math.pi * day / 365)
            short_cycle = .25 * math.sin(2 * math.pi * day / 61)
            values.append(f'{base * (1 + amplitude * (cycle + short_cycle + noise)):.6f}')
        indices[name] = values
    return {'synthetic': True, 'start_date': '2026-01-01', 'indices': indices}


if __name__ == '__main__':
    DESTINATION.write_text(json.dumps(generate(), ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8', newline='\n')
