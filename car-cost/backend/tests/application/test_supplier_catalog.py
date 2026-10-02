"""Les fournisseurs d'une nomenclature, et les pièces que chacun vend."""

from __future__ import annotations

from decimal import Decimal

from carcost.application.scenario import Plant, Sourcing, SupplierOffer
from carcost.application.supplier_catalog import suppliers_of
from carcost.domain.bom import Bom, Edge
from factories import manufactured, purchased


def _bom() -> Bom:
    return Bom(
        root_ref="V",
        parts={"V": manufactured("V"), "S": purchased("S"), "T": purchased("T")},
        edges=(Edge("V", "S", Decimal("2")), Edge("V", "T", Decimal("1"))),
    )


def _sourcing() -> Sourcing:
    return Sourcing(
        offers={
            "S": (
                SupplierOffer("SUP-A", Decimal("1.0"), True, "Alpha"),
                SupplierOffer("SUP-B", Decimal("0.9"), False, "Beta"),
            ),
            "T": (SupplierOffer("SUP-A", Decimal("1.1"), True, "Alpha"),),
            # Une offre sur une pièce absente de la nomenclature : un autre
            # véhicule la vend, ce fournisseur ne vend rien à celui-ci par elle.
            "X": (SupplierOffer("SUP-C", Decimal("1.0"), True, "Gamma"),),
        },
        plants={
            "SUP-A": (Plant("PLT-A", "SUP-A", "GB", Decimal("1"), Decimal("0.01"), True, "Coventry", 8),),
            "SUP-B": (Plant("PLT-B", "SUP-B", "DE", Decimal("1"), Decimal("0.05"), True, "Hagen", 15),),
            "SUP-C": (Plant("PLT-C", "SUP-C", "IT", Decimal("1"), Decimal("0.07"), True, "Turin", 9),),
        },
    )


def test_each_supplier_lists_the_parts_it_sells_for_this_bom():
    entries = {entry.supplier_id: entry for entry in suppliers_of(_bom(), _sourcing())}

    assert set(entries) == {"SUP-A", "SUP-B"}
    assert [part.part_ref for part in entries["SUP-A"].parts] == ["S", "T"]
    assert entries["SUP-A"].name == "Alpha"
    assert entries["SUP-A"].default_count == 2
    assert entries["SUP-B"].default_count == 0


def test_an_offer_keeps_its_multiplier_and_whether_it_is_retained():
    beta = next(e for e in suppliers_of(_bom(), _sourcing()) if e.supplier_id == "SUP-B")
    (part,) = beta.parts
    assert part.price_multiplier == Decimal("0.9")
    assert part.is_default is False


def test_plants_come_with_their_supplier():
    alpha = next(e for e in suppliers_of(_bom(), _sourcing()) if e.supplier_id == "SUP-A")
    assert [plant.label for plant in alpha.plants] == ["Coventry"]


def test_suppliers_are_ordered_by_name():
    assert [e.name for e in suppliers_of(_bom(), _sourcing())] == ["Alpha", "Beta"]
