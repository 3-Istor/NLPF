"""La prise de snapshot et le repli sur panne de l'API de prix.

Règle commune aux trois modes de panne : jamais de plantage, jamais de silence,
jamais de zéro inventé.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from carcost.application.ports import PriceSourceTimeout, Quote
from carcost.application.take_snapshot import (
    NoPriceAvailable,
    SnapshotTaken,
    TookFallback,
    take_snapshot,
)
from carcost.domain.prices import PriceSnapshot, SnapshotStatus

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
REFS = ("SCREW", "PANEL")


class FakeSource:
    """Une source de prix qui répond, ou qui ne répond pas."""

    def __init__(self, prices=None, *, timeout=False):
        self.prices = prices or {"SCREW": "0.500000", "PANEL": "12.400000"}
        self.timeout = timeout
        self.calls = 0

    def fetch(self, refs, currency):
        self.calls += 1
        if self.timeout:
            raise PriceSourceTimeout("aucune réponse en 2,0 s")
        return [
            Quote(part_ref=ref, price=Decimal(self.prices[ref]), raw=self.prices[ref])
            for ref in refs
        ]


def previous_snapshot(taken_at=NOW - timedelta(hours=3)) -> PriceSnapshot:
    return PriceSnapshot(
        id="snp-hier",
        taken_at=taken_at,
        currency="EUR",
        source="mock",
        prices={"SCREW": Decimal("0.480000"), "PANEL": Decimal("12.100000")},
    )


class TestNominal:
    def test_takes_a_fresh_snapshot(self):
        outcome = take_snapshot(
            FakeSource(), refs=REFS, currency="EUR", previous=None, now=NOW,
            snapshot_id="snp-1",
        )

        assert isinstance(outcome, SnapshotTaken)
        assert outcome.snapshot.status(NOW) is SnapshotStatus.FRESH
        assert outcome.snapshot.prices["SCREW"] == Decimal("0.500000")

    def test_the_new_snapshot_does_not_touch_the_previous_one(self):
        previous = previous_snapshot()

        take_snapshot(
            FakeSource(), refs=REFS, currency="EUR", previous=previous, now=NOW,
            snapshot_id="snp-2",
        )

        assert previous.prices["SCREW"] == Decimal("0.480000")

    def test_a_snapshot_cannot_be_modified_after_the_fact(self):
        snapshot = previous_snapshot()

        with pytest.raises(Exception):
            snapshot.taken_at = NOW


class TestTimeout:
    def test_falls_back_to_the_last_valid_snapshot(self):
        previous = previous_snapshot()

        outcome = take_snapshot(
            FakeSource(timeout=True), refs=REFS, currency="EUR", previous=previous,
            now=NOW, snapshot_id="snp-3",
        )

        assert isinstance(outcome, TookFallback)
        assert outcome.snapshot is previous
        assert "aucune réponse" in outcome.reason

    def test_the_fallback_says_how_old_the_prices_are(self):
        outcome = take_snapshot(
            FakeSource(timeout=True), refs=REFS, currency="EUR",
            previous=previous_snapshot(), now=NOW, snapshot_id="snp-4",
        )

        assert outcome.snapshot.age(NOW) == timedelta(hours=3)

    def test_no_new_snapshot_is_fabricated(self):
        """Un repli réutilise le snapshot d'hier ; il n'en invente pas un
        nouveau qui porterait la date du jour et les prix de la veille."""
        outcome = take_snapshot(
            FakeSource(timeout=True), refs=REFS, currency="EUR",
            previous=previous_snapshot(), now=NOW, snapshot_id="snp-5",
        )

        assert outcome.snapshot.id == "snp-hier"
        assert outcome.snapshot.taken_at < NOW

    def test_without_any_previous_snapshot_it_refuses_rather_than_guesses(self):
        with pytest.raises(NoPriceAvailable):
            take_snapshot(
                FakeSource(timeout=True), refs=REFS, currency="EUR", previous=None,
                now=NOW, snapshot_id="snp-6",
            )

    def test_the_source_is_called_once_not_retried_forever(self):
        source = FakeSource(timeout=True)

        take_snapshot(
            source, refs=REFS, currency="EUR", previous=previous_snapshot(),
            now=NOW, snapshot_id="snp-7",
        )

        assert source.calls == 1


class TestAgeAndStaleness:
    def test_under_twenty_four_hours_is_fresh(self):
        snapshot = previous_snapshot(taken_at=NOW - timedelta(hours=23, minutes=59))

        assert snapshot.status(NOW) is SnapshotStatus.FRESH

    def test_beyond_twenty_four_hours_is_stale(self):
        snapshot = previous_snapshot(taken_at=NOW - timedelta(hours=24, seconds=1))

        assert snapshot.status(NOW) is SnapshotStatus.STALE

    def test_a_stale_snapshot_still_serves_prices(self):
        """Un snapshot périmé n'empêche pas de calculer : il marque le résultat.
        S'il bloquait, une coupure d'API d'une journée rendrait l'outil
        inutilisable."""
        snapshot = previous_snapshot(taken_at=NOW - timedelta(days=4))

        assert snapshot.status(NOW) is SnapshotStatus.STALE
        assert snapshot.prices["SCREW"] == Decimal("0.480000")
