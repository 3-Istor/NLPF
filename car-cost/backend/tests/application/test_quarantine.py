"""Ce que devient un prix aberrant, et un prix qui manque.

Deux règles, et elles ne se négocient pas : une valeur douteuse n'entre pas
dans un snapshot, et une valeur absente ne devient jamais zéro. Dans les deux
cas on le dit — la ligne concernée, le snapshot, et le calcul qui s'en sert.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from carcost.application.ports import Quote
from carcost.application.take_snapshot import SnapshotTaken, take_snapshot
from carcost.domain.prices import PriceSnapshot, SnapshotStatus

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
REFS = ("SCREW", "PANEL")


class Source:
    """Une source qui répond ce qu'on lui dit de répondre."""

    def __init__(self, *quotes: Quote):
        self.quotes = quotes

    def fetch(self, refs, currency):
        return self.quotes


def yesterday() -> PriceSnapshot:
    return PriceSnapshot(
        id="snp-hier",
        taken_at=NOW - timedelta(hours=3),
        currency="EUR",
        source="mock",
        prices={"SCREW": Decimal("0.500000"), "PANEL": Decimal("12.000000")},
    )


#: Sentinelle : sans elle, `previous=None` retombait sur le snapshot de la
#: veille et le cas « aucun historique » n'était jamais joué.
_HIER = object()


def take(*quotes: Quote, previous=_HIER):
    return take_snapshot(
        Source(*quotes),
        refs=REFS,
        currency="EUR",
        previous=yesterday() if previous is _HIER else previous,
        now=NOW,
        snapshot_id="snp-1",
    )


def good(ref: str, price: str) -> Quote:
    return Quote(part_ref=ref, price=Decimal(price), raw=price)


class TestAbsurdValues:
    @pytest.mark.parametrize(
        ("price", "why"),
        [("-42.000000", "négatif"), ("0.000000", "nul sur une pièce achetée")],
    )
    def test_an_impossible_price_never_enters_the_snapshot(self, price, why):
        outcome = take(good("SCREW", price), good("PANEL", "12.000000"))

        assert isinstance(outcome, SnapshotTaken)
        assert outcome.snapshot.prices["SCREW"] == Decimal("0.500000"), why

    def test_the_rejected_value_is_journalised_with_its_reason(self):
        outcome = take(good("SCREW", "-42.000000"), good("PANEL", "12.000000"))

        quarantined = outcome.quarantined[0]
        assert quarantined.part_ref == "SCREW"
        assert quarantined.rejected_value == "-42.000000"
        assert "négatif" in quarantined.reason.lower()
        assert quarantined.replacement == Decimal("0.500000")

    def test_a_price_that_leapt_is_held_back(self):
        """0,50 € qui devient 9 999 € : c'est une erreur de source, pas une
        hausse. On garde l'ancien et on le signale."""
        outcome = take(good("SCREW", "9999.000000"), good("PANEL", "12.000000"))

        assert outcome.snapshot.prices["SCREW"] == Decimal("0.500000")
        assert "écart" in outcome.quarantined[0].reason.lower()

    def test_a_plausible_move_passes(self):
        """+20 % est une variation, pas une aberration. Un seuil trop serré
        met tout en quarantaine et l'outil paraît cassé."""
        outcome = take(good("SCREW", "0.600000"), good("PANEL", "12.000000"))

        assert outcome.snapshot.prices["SCREW"] == Decimal("0.600000")
        assert outcome.quarantined == ()

    def test_a_non_numeric_answer_is_quarantined_not_crashed(self):
        outcome = take(
            Quote(part_ref="SCREW", price=None, raw="n/a", reason="valeur non numérique"),
            good("PANEL", "12.000000"),
        )

        assert outcome.quarantined[0].rejected_value == "n/a"
        assert outcome.snapshot.prices["SCREW"] == Decimal("0.500000")


class TestDegradedSnapshot:
    def test_a_snapshot_with_a_fallback_line_is_degraded(self):
        outcome = take(good("SCREW", "-1.000000"), good("PANEL", "12.000000"))

        assert outcome.snapshot.status(NOW) is SnapshotStatus.DEGRADED
        assert outcome.snapshot.fallback_refs == frozenset({"SCREW"})

    def test_a_clean_snapshot_is_fresh(self):
        outcome = take(good("SCREW", "0.520000"), good("PANEL", "12.000000"))

        assert outcome.snapshot.status(NOW) is SnapshotStatus.FRESH
        assert outcome.snapshot.fallback_refs == frozenset()


class TestMissingPrices:
    def test_a_missing_answer_falls_back_on_the_last_known_price(self):
        outcome = take(good("PANEL", "12.000000"))

        assert outcome.snapshot.prices["SCREW"] == Decimal("0.500000")
        assert "SCREW" in outcome.snapshot.fallback_refs

    def test_without_any_history_the_part_stays_without_a_price(self):
        """Pas de zéro, pas d'interpolation, pas de prix d'une pièce voisine :
        la pièce est nommée, et le calcul qui la rencontre sera incomplet."""
        outcome = take(good("PANEL", "12.000000"), previous=None)

        assert "SCREW" not in outcome.snapshot.prices
        assert outcome.missing == ("SCREW",)

    def test_a_snapshot_missing_a_price_says_so(self):
        outcome = take(good("PANEL", "12.000000"), previous=None)

        assert outcome.snapshot.status(NOW) is SnapshotStatus.DEGRADED


class TestRefusedOrAbsent:
    """Deux replis, deux vérifications différentes pour qui lit la ligne.

    Une valeur refusée appelle un coup d'œil au journal ; une pièce absente de
    la réponse, une question à la source. Le snapshot garde donc la différence.
    """

    def test_a_refused_value_is_remembered_as_quarantined(self):
        outcome = take(good("SCREW", "-42.000000"), good("PANEL", "12.000000"))

        assert outcome.snapshot.quarantined_refs == frozenset({"SCREW"})
        assert outcome.snapshot.fallback_refs == frozenset({"SCREW"})

    def test_an_absent_part_falls_back_without_being_quarantined(self):
        outcome = take(good("PANEL", "12.000000"))

        assert outcome.snapshot.fallback_refs == frozenset({"SCREW"})
        assert outcome.snapshot.quarantined_refs == frozenset()
