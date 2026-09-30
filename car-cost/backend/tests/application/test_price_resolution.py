"""Le prix unitaire d'une pièce achetée, et ce que le scénario en fait.

    prix unitaire = référence × multiplicateur fournisseur × coefficient d'usine

Les trois facteurs restent séparés jusqu'au bout : c'est ce qui permet de dire
ce que coûte le choix de l'usine indépendamment du fournisseur (ADR-0010).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from carcost.application.price_resolution import (
    ParameterNotApplicable,
    PlantNotAvailableForSupplier,
    PriceOverrideNeedsJustification,
    resolve_unit_prices,
)
from carcost.application.scenario import (
    Plant,
    Scenario,
    ScenarioParameter,
    Sourcing,
    SupplierOffer,
)
from carcost.domain.bom import Bom, Edge
from carcost.domain.prices import PriceSnapshot
from factories import manufactured, purchased

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def bom() -> Bom:
    return Bom(
        root_ref="V",
        parts={"V": manufactured("V", labour="60"), "S": purchased("S")},
        edges=(Edge("V", "S", Decimal("4")),),
    )


@pytest.fixture
def sourcing() -> Sourcing:
    """Deux fournisseurs pour la vis ; le premier a deux usines."""
    return Sourcing(
        offers={
            "S": (
                SupplierOffer("SUP-IT", Decimal("1.080000"), is_default=True),
                SupplierOffer("SUP-DE", Decimal("1.140000"), is_default=False),
            )
        },
        plants={
            "SUP-IT": (
                Plant("PLT-IT", "SUP-IT", "IT", Decimal("1.000000"),
                      Decimal("0.021000"), is_default=True),
                Plant("PLT-TR", "SUP-IT", "TR", Decimal("0.920000"),
                      Decimal("0.142000"), is_default=False),
            ),
            "SUP-DE": (
                Plant("PLT-DE", "SUP-DE", "DE", Decimal("1.000000"),
                      Decimal("0.046000"), is_default=True),
            ),
        },
    )


@pytest.fixture
def snapshot() -> PriceSnapshot:
    return PriceSnapshot(
        id="snp-1", taken_at=NOW, currency="EUR", source="mock",
        prices={"S": Decimal("40.000000")},
    )


def scenario(*parameters: ScenarioParameter) -> Scenario:
    return Scenario(
        id="scn",
        bom_version="bom-test",
        display_currency="EUR",
        labour_rate=Decimal("42.00"),
        active_rules=frozenset({"labour"}),
        parameters=parameters,
    )


def parameter(**overrides) -> ScenarioParameter:
    base = {
        "part_ref": "S",
        "scope": "part",
        "path": None,
        "supplier_id": None,
        "plant_id": None,
        "price_override": None,
        "price_override_justification": None,
        "labour_minutes": None,
    }
    return ScenarioParameter(**{**base, **overrides})


class TestDefaults:
    def test_an_empty_scenario_uses_the_default_supplier_and_plant(
        self, bom, sourcing, snapshot
    ):
        resolved = resolve_unit_prices(bom, sourcing, snapshot, scenario())

        assert resolved.prices["S"] == Decimal("43.200000")  # 40 × 1,08 × 1,00
        assert resolved.explanations["S"].supplier_id == "SUP-IT"
        assert resolved.explanations["S"].plant_id == "PLT-IT"

    def test_the_three_factors_stay_readable_separately(
        self, bom, sourcing, snapshot
    ):
        """« Que me coûte cette usine ? » doit avoir une réponse."""
        explanation = resolve_unit_prices(
            bom, sourcing, snapshot, scenario()
        ).explanations["S"]

        assert explanation.reference_price == Decimal("40.000000")
        assert explanation.supplier_multiplier == Decimal("1.080000")
        assert explanation.plant_coefficient == Decimal("1.000000")


class TestTwoIndependentLevers:
    def test_changing_the_plant_without_changing_the_supplier(
        self, bom, sourcing, snapshot
    ):
        """C'est la décision M1 : même fournisseur, usine différente."""
        resolved = resolve_unit_prices(
            bom, sourcing, snapshot,
            scenario(parameter(supplier_id="SUP-IT", plant_id="PLT-TR")),
        )

        assert resolved.prices["S"] == Decimal("39.744000")  # 40 × 1,08 × 0,92
        assert resolved.explanations["S"].origin_country == "TR"

    def test_changing_the_supplier_falls_back_on_its_default_plant(
        self, bom, sourcing, snapshot
    ):
        resolved = resolve_unit_prices(
            bom, sourcing, snapshot, scenario(parameter(supplier_id="SUP-DE"))
        )

        assert resolved.explanations["S"].plant_id == "PLT-DE"
        assert resolved.prices["S"] == Decimal("45.600000")  # 40 × 1,14 × 1,00

    def test_a_plant_of_another_supplier_is_refused(self, bom, sourcing, snapshot):
        with pytest.raises(PlantNotAvailableForSupplier):
            resolve_unit_prices(
                bom, sourcing, snapshot,
                scenario(parameter(supplier_id="SUP-DE", plant_id="PLT-TR")),
            )


class TestOverride:
    def test_a_forced_price_replaces_the_three_factors(self, bom, sourcing, snapshot):
        resolved = resolve_unit_prices(
            bom, sourcing, snapshot,
            scenario(parameter(
                price_override=Decimal("29.990000"),
                price_override_justification="devis du 2026-09-20",
            )),
        )

        assert resolved.prices["S"] == Decimal("29.990000")
        assert resolved.explanations["S"].override_justification == "devis du 2026-09-20"

    def test_a_forced_price_without_justification_is_refused(
        self, bom, sourcing, snapshot
    ):
        with pytest.raises(PriceOverrideNeedsJustification):
            resolve_unit_prices(
                bom, sourcing, snapshot,
                scenario(parameter(price_override=Decimal("1.000000"))),
            )


class TestValuationMode:
    def test_a_supplier_on_a_manufactured_part_is_refused(
        self, bom, sourcing, snapshot
    ):
        """Un ensemble n'a pas de fournisseur : lui en donner un serait
        proposer une double comptabilisation (ADR-0008)."""
        with pytest.raises(ParameterNotApplicable):
            resolve_unit_prices(
                bom, sourcing, snapshot,
                scenario(parameter(part_ref="V", supplier_id="SUP-IT")),
            )

    def test_labour_minutes_on_a_purchased_part_is_refused(
        self, bom, sourcing, snapshot
    ):
        with pytest.raises(ParameterNotApplicable):
            resolve_unit_prices(
                bom, sourcing, snapshot,
                scenario(parameter(labour_minutes=Decimal("5"))),
            )

    def test_no_price_is_resolved_for_a_manufactured_part(
        self, bom, sourcing, snapshot
    ):
        resolved = resolve_unit_prices(bom, sourcing, snapshot, scenario())

        assert "V" not in resolved.prices


class TestMissingPrice:
    def test_a_part_absent_from_the_snapshot_is_reported_not_zeroed(self, bom, sourcing):
        empty = PriceSnapshot(
            id="snp-vide", taken_at=NOW, currency="EUR", source="mock", prices={}
        )

        resolved = resolve_unit_prices(bom, sourcing, empty, scenario())

        assert resolved.missing == ("S",)
        assert "S" not in resolved.prices


class TestCarbon:
    """L'intensité de transport (ADR-0010, cadrage.md A10) se résout par la
    même offre et la même usine que le prix : jamais une seconde résolution de
    sourcing, qui pourrait diverger de celle qui a servi au prix."""

    def test_the_default_plant_s_intensity_is_resolved_alongside_the_price(
        self, bom, sourcing, snapshot
    ):
        resolved = resolve_unit_prices(bom, sourcing, snapshot, scenario())

        assert resolved.transport_co2_per_kg["S"] == Decimal("0.021000")

    def test_changing_the_plant_changes_the_intensity_too(
        self, bom, sourcing, snapshot
    ):
        """Même levier que pour le prix : changer d'usine change le transport."""
        resolved = resolve_unit_prices(
            bom, sourcing, snapshot,
            scenario(parameter(supplier_id="SUP-IT", plant_id="PLT-TR")),
        )

        assert resolved.transport_co2_per_kg["S"] == Decimal("0.142000")

    def test_a_forced_price_has_no_known_transport(self, bom, sourcing, snapshot):
        """Un prix forcé ne retient aucune usine : rien à annoncer, pas zéro."""
        resolved = resolve_unit_prices(
            bom, sourcing, snapshot,
            scenario(parameter(
                price_override=Decimal("29.990000"),
                price_override_justification="devis du 2026-09-20",
            )),
        )

        assert "S" not in resolved.transport_co2_per_kg

    def test_a_missing_price_has_no_transport_either(self, bom, sourcing):
        empty = PriceSnapshot(
            id="snp-vide", taken_at=NOW, currency="EUR", source="mock", prices={}
        )

        resolved = resolve_unit_prices(bom, sourcing, empty, scenario())

        assert "S" not in resolved.transport_co2_per_kg
