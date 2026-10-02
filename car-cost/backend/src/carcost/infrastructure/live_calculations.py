"""Les calculs en direct : en mémoire, jamais en base (ADR-0015).

Un calcul en direct cite un snapshot de prix qui n'existe pas en base et se
refait toutes les quelques secondes : l'enregistrer remplirait la table de
totaux que personne n'a demandé à garder. Mais l'arbre relit les lignes d'un
calcul par son identifiant ; on garde donc les derniers, en nombre borné, le
temps qu'il le fasse. Un redémarrage les oublie, et c'est voulu.
"""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock

from ..application.ports import CalculationNotFound

#: Assez pour quelques écrans ouverts qui rafraîchissent toutes les 5 s.
CAPACITY = 64


class LiveCalculations:
    def __init__(self, capacity: int = CAPACITY) -> None:
        self.capacity = capacity
        self._items: OrderedDict[str, object] = OrderedDict()
        self._lock = Lock()

    def keep(self, calculation) -> None:
        with self._lock:
            self._items[calculation.id] = calculation
            self._items.move_to_end(calculation.id)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)

    def get(self, calculation_id: str):
        with self._lock:
            return self._items.get(calculation_id)


class WithLiveCalculations:
    """Le dépôt des calculs, qui sait aussi lire un calcul en direct récent.

    Seule la lecture par identifiant les voit : « le dernier calcul d'un
    scénario » reste le dernier calcul **enregistré**, sinon un total en
    direct passerait pour le résultat du scénario.
    """

    def __init__(self, inner, live: LiveCalculations) -> None:
        self._inner = inner
        self._live = live

    def get(self, calculation_id: str):
        found = self._live.get(calculation_id)
        if found is not None:
            return found
        return self._inner.get(calculation_id)

    def __getattr__(self, name):
        return getattr(self._inner, name)


__all__ = ["CalculationNotFound", "LiveCalculations", "WithLiveCalculations"]
