"""Fabriques de pièces pour les tests de domaine."""

from __future__ import annotations

from decimal import Decimal

from carcost.domain.bom import Part, ValuationMode


def purchased(ref: str, *, carbon: str = "0") -> Part:
    return Part(
        ref=ref,
        label=ref,
        system="TST",
        unit="pce",
        valuation_mode=ValuationMode.PURCHASED,
        carbon_factor=Decimal(carbon),
        mass_kg=Decimal("1"),
    )


def manufactured(ref: str, *, labour: str = "0", carbon: str = "0") -> Part:
    return Part(
        ref=ref,
        label=ref,
        system="TST",
        unit="pce",
        valuation_mode=ValuationMode.MANUFACTURED,
        carbon_factor=Decimal(carbon),
        labour_minutes=Decimal(labour),
    )
