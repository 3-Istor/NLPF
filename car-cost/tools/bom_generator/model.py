"""Types du jeu de données et constructeur de nomenclature.

Aucune entrée/sortie ici : ce module ne connaît ni fichier, ni base, ni réseau.
Il fait respecter, à la construction, les règles qu'aucun fichier ne doit violer
(ADR-0008) et refuse le graphe dès qu'une d'elles tombe.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

PURCHASED = "purchased"
MANUFACTURED = "manufactured"

# Émissions de procédé d'un ensemble fabriqué, par minute de main-d'œuvre.
# Approximation déclarée : l'énergie d'atelier est supposée proportionnelle au
# temps passé. Valeur synthétique (voir les métadonnées du jeu de données).
PROCESS_CO2_PER_LABOUR_MINUTE = Decimal("0.05")


def dec(value) -> Decimal:
    """Décimal exact depuis une chaîne ou un entier (ADR-0011). Jamais de float."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError(
            f"valeur flottante interdite ({value!r}) : passer une chaîne, ADR-0011"
        )
    return Decimal(str(value))


@dataclass(frozen=True)
class Part:
    ref: str
    label: str
    category: str
    system: str
    unit: str
    valuation_mode: str
    # Émissions PROPRES de la pièce, par unité :
    #   - achetée      : son empreinte, de l'extraction à la sortie d'usine ;
    #   - fabriquée    : les seules émissions du procédé d'assemblage.
    # Les enfants ne sont jamais inclus ici, sinon le CO2 serait compté deux fois.
    carbon_factor: Decimal
    labour_minutes: Decimal | None = None
    base_price_eur: Decimal | None = None
    price_per: Decimal = Decimal(1)
    material_ref: str | None = None
    mass_kg: Decimal | None = None


@dataclass(frozen=True)
class Edge:
    parent_ref: str
    child_ref: str
    quantity: Decimal
    unit: str
    # Pièces de rechange livrées avec le véhicule (SAV). Elles ne sont pas
    # montées : elles n'entrent dans la quantité que si le scénario le demande.
    after_sales: Decimal = Decimal(0)


@dataclass(frozen=True)
class Bom:
    root_ref: str
    parts: dict[str, Part]
    edges: tuple[Edge, ...]

    def children_of(self, ref: str) -> tuple[Edge, ...]:
        return tuple(e for e in self.edges if e.parent_ref == ref)

    def parents_of(self, ref: str) -> tuple[str, ...]:
        return tuple(e.parent_ref for e in self.edges if e.child_ref == ref)


class BomError(Exception):
    """Le graphe décrit viole une règle de structure : il ne doit pas exister."""


class BomBuilder:
    def __init__(self) -> None:
        self._parts: dict[str, Part] = {}
        # parent, enfant, quantité, quantité SAV
        self._pending: list[tuple[str, str, Decimal, Decimal]] = []

    # ------------------------------------------------------------------ pièces

    def purchased(
        self,
        ref: str,
        label: str,
        *,
        system: str,
        category: str,
        unit: str,
        price: str,
        carbon: str,
        mass: str,
        per: str | int = 1,
    ) -> str:
        """Une pièce achetée : elle porte un prix et n'aura jamais d'enfant."""
        self._declare(
            Part(
                ref=ref,
                label=label,
                category=category,
                system=system,
                unit=unit,
                valuation_mode=PURCHASED,
                carbon_factor=dec(carbon),
                base_price_eur=dec(price),
                price_per=dec(per),
                mass_kg=dec(mass),
            )
        )
        return ref

    def assembly(
        self,
        ref: str,
        label: str,
        *,
        system: str,
        category: str,
        labour: str | int,
        children: Mapping[str, str | int],
        unit: str = "pce",
        material: str | None = None,
        carbon: str | None = None,
        after_sales: Mapping[str, str | int] | None = None,
    ) -> str:
        """Un ensemble fabriqué : il porte de la main-d'œuvre et jamais de prix."""
        labour_minutes = dec(labour)
        self._declare(
            Part(
                ref=ref,
                label=label,
                category=category,
                system=system,
                unit=unit,
                valuation_mode=MANUFACTURED,
                carbon_factor=(
                    dec(carbon)
                    if carbon is not None
                    else labour_minutes * PROCESS_CO2_PER_LABOUR_MINUTE
                ),
                labour_minutes=labour_minutes,
                material_ref=material,
            )
        )
        if not children:
            raise BomError(f"{ref} : un ensemble fabriqué sans enfant n'a pas de coût")
        after_sales = after_sales or {}
        for child_ref, quantity in children.items():
            self._pending.append(
                (ref, child_ref, dec(quantity), dec(after_sales.get(child_ref, 0)))
            )
        return ref

    def _declare(self, part: Part) -> None:
        if part.ref in self._parts:
            raise BomError(f"référence déclarée deux fois : {part.ref}")
        self._parts[part.ref] = part

    # ------------------------------------------------------------------ finition

    def build(self, root_ref: str) -> Bom:
        """Résout les arêtes et refuse le graphe s'il viole une règle de structure.

        L'unité d'une arête est celle de l'enfant : une nomenclature ne peut pas
        demander « 4 kg de vis M6 » si la vis se compte en pièces.
        """
        seen: set[tuple[str, str]] = set()
        edges: list[Edge] = []

        for parent_ref, child_ref, quantity, after_sales in self._pending:
            if child_ref not in self._parts:
                raise BomError(f"{parent_ref} → {child_ref} : enfant jamais déclaré")
            if parent_ref == child_ref:
                raise BomError(f"{parent_ref} : une pièce ne se contient pas elle-même")
            if quantity <= 0:
                raise BomError(f"{parent_ref} → {child_ref} : quantité {quantity} ≤ 0")
            if after_sales < 0:
                raise BomError(
                    f"{parent_ref} → {child_ref} : quantité SAV {after_sales} < 0"
                )
            key = (parent_ref, child_ref)
            if key in seen:
                raise BomError(f"arête en double : {parent_ref} → {child_ref}")
            seen.add(key)
            edges.append(
                Edge(
                    parent_ref=parent_ref,
                    child_ref=child_ref,
                    quantity=quantity,
                    unit=self._parts[child_ref].unit,
                    after_sales=after_sales,
                )
            )

        # ADR-0008, contrôlé ici et pas seulement espéré : une pièce achetée est
        # une feuille. La violation est impossible par construction (seule
        # `assembly` crée des arêtes), mais on le vérifie quand même — c'est la
        # règle dont l'oubli coûte le plus cher.
        for edge in edges:
            parent = self._parts[edge.parent_ref]
            if parent.valuation_mode != MANUFACTURED:
                raise BomError(
                    f"{parent.ref} est achetée et porte un enfant ({edge.child_ref})"
                )

        if root_ref not in self._parts:
            raise BomError(f"racine inconnue : {root_ref}")

        edges.sort(key=lambda e: (e.parent_ref, e.child_ref))
        return Bom(
            root_ref=root_ref,
            parts=dict(sorted(self._parts.items())),
            edges=tuple(edges),
        )
