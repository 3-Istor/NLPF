"""Qui vend quoi pour une nomenclature : le sourcing, lu par fournisseur.

Le sourcing est rangé par pièce (« qui peut me fournir cette vis ? »). La page
Fournisseurs pose la question inverse ; on retourne l'index, sans rien choisir
ni calculer : le fournisseur retenu reste celui du jeu de données ou du
scénario (ADR-0010).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..domain.bom import Bom
from .scenario import Plant, Sourcing


@dataclass(frozen=True)
class SuppliedPart:
    part_ref: str
    label: str
    unit: str
    system: str
    price_multiplier: Decimal
    #: Fournisseur retenu par défaut pour cette pièce.
    is_default: bool


@dataclass(frozen=True)
class SupplierEntry:
    supplier_id: str
    name: str
    plants: tuple[Plant, ...]
    parts: tuple[SuppliedPart, ...]

    @property
    def default_count(self) -> int:
        return sum(1 for part in self.parts if part.is_default)


def suppliers_of(bom: Bom, sourcing: Sourcing) -> tuple[SupplierEntry, ...]:
    """Les fournisseurs qui vendent au moins une pièce de cette nomenclature.

    Une offre sur une pièce absente de la nomenclature est ignorée : la table
    des fournisseurs est commune à tous les véhicules.
    """
    names: dict[str, str] = {}
    parts: dict[str, list[SuppliedPart]] = {}
    for part_ref in sorted(sourcing.offers):
        part = bom.parts.get(part_ref)
        if part is None:
            continue
        for offer in sourcing.offers[part_ref]:
            names.setdefault(offer.supplier_id, offer.name or offer.supplier_id)
            parts.setdefault(offer.supplier_id, []).append(
                SuppliedPart(
                    part_ref=part_ref,
                    label=part.label,
                    unit=part.unit,
                    system=part.system,
                    price_multiplier=offer.price_multiplier,
                    is_default=offer.is_default,
                )
            )
    return tuple(
        sorted(
            (
                SupplierEntry(
                    supplier_id=supplier_id,
                    name=names[supplier_id],
                    plants=tuple(sourcing.plants.get(supplier_id, ())),
                    parts=tuple(supplied),
                )
                for supplier_id, supplied in parts.items()
            ),
            key=lambda entry: (entry.name.casefold(), entry.supplier_id),
        )
    )
