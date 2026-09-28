"""Une version de nomenclature, relue une fois par processus.

Sans cache, chaque dépliage relisait 474 pièces et 689 arêtes, sur une connexion
neuve. Garder le graphe en mémoire n'est juste que parce qu'une version validée
ne change plus : la base le refuse (ADR-0012). Le cache n'a donc pas
d'expiration, et n'en a pas besoin.

Seuls les succès sont gardés : une version inconnue ou pas encore validée peut
le devenir pendant que le serveur tourne.
"""

from __future__ import annotations

from threading import Lock

from ..application.ports import BomRepository


class CachedBomRepository:
    def __init__(self, inner: BomRepository) -> None:
        self._inner = inner
        self._boms: dict[str, object] = {}
        # FastAPI sert les routes synchrones depuis un pool de threads : sans
        # verrou, dix dépliages simultanés au démarrage feraient dix lectures.
        self._lock = Lock()

    def load(self, version: str):
        bom = self._boms.get(version)
        if bom is not None:
            return bom
        with self._lock:
            if version not in self._boms:
                self._boms[version] = self._inner.load(version)
            return self._boms[version]

    def versions(self):
        return self._inner.versions()
