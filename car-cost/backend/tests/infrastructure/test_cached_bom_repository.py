"""Le cache de nomenclature.

Garder une version en mémoire n'est juste que parce qu'une version validée ne
change plus (ADR-0013). Ce qui n'est pas encore validé, ou pas encore chargé,
doit donc être redemandé à chaque fois : le cache ne doit pas figer un refus.
"""

from __future__ import annotations

from carcost.application.ports import BomVersionNotFound, BomVersionNotValidated
from carcost.infrastructure.cached_bom_repository import CachedBomRepository


class CountingRepository:
    def __init__(self):
        self.loads = 0
        self.known: dict[str, object] = {}
        self.pending: set[str] = set()

    def load(self, version: str):
        self.loads += 1
        if version in self.pending:
            raise BomVersionNotValidated(version)
        if version not in self.known:
            raise BomVersionNotFound(version)
        return self.known[version]

    def versions(self):
        return ("listed", self.loads)


def test_a_validated_version_is_read_once():
    inner = CountingRepository()
    inner.known["v1"] = object()
    cache = CachedBomRepository(inner)

    first = cache.load("v1")
    second = cache.load("v1")

    assert first is second
    assert inner.loads == 1


def test_each_version_is_cached_separately():
    """Deux clients sur deux versions ne se marchent pas dessus."""
    inner = CountingRepository()
    inner.known.update(v1=object(), v2=object())
    cache = CachedBomRepository(inner)

    assert cache.load("v1") is not cache.load("v2")
    assert inner.loads == 2


def test_an_unknown_version_is_asked_again_once_it_exists():
    inner = CountingRepository()
    cache = CachedBomRepository(inner)
    try:
        cache.load("v1")
    except BomVersionNotFound:
        pass
    inner.known["v1"] = object()

    assert cache.load("v1") is inner.known["v1"]


def test_a_version_pending_validation_is_asked_again_once_validated():
    inner = CountingRepository()
    inner.known["v1"] = object()
    inner.pending.add("v1")
    cache = CachedBomRepository(inner)
    try:
        cache.load("v1")
    except BomVersionNotValidated:
        pass
    inner.pending.clear()

    assert cache.load("v1") is inner.known["v1"]


def test_the_list_of_versions_is_never_cached():
    """Une version chargée pendant que le serveur tourne doit apparaître."""
    inner = CountingRepository()
    inner.known["v1"] = object()
    cache = CachedBomRepository(inner)

    cache.versions()
    cache.load("v1")

    assert cache.versions() == ("listed", 1)
