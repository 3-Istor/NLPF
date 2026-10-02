"""Le scénario : ce que l'utilisateur règle, et le catalogue de sourcing.

Un paramètre porte toujours sa **portée**, explicite et jamais déduite : soit il
vaut pour toutes les occurrences de la pièce, soit pour une occurrence désignée
par son chemin (ADR-0002). L'interface doit pouvoir dire laquelle, donc le
modèle doit la porter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Mapping, Sequence

Scope = Literal["part", "path"]


@dataclass(frozen=True)
class SupplierOffer:
    supplier_id: str
    price_multiplier: Decimal
    is_default: bool
    #: Le nom lisible. L'écran affiche « Meccanica Torinese », pas un
    #: identifiant : on choisit un fournisseur, pas une clé primaire.
    name: str = ""


@dataclass(frozen=True)
class Plant:
    plant_id: str
    supplier_id: str
    origin_country: str
    price_coefficient: Decimal
    transport_co2_kg_per_kg: Decimal
    is_default: bool
    label: str = ""
    #: Le délai fait partie du choix : une usine moins chère et plus lente n'est
    #: pas la même offre. L'afficher à zéro reviendrait à le cacher.
    lead_time_days: int = 0


@dataclass(frozen=True)
class Sourcing:
    """Qui peut fournir quoi, et depuis où."""

    offers: Mapping[str, Sequence[SupplierOffer]]
    plants: Mapping[str, Sequence[Plant]]

    def offers_for(self, part_ref: str) -> Sequence[SupplierOffer]:
        return self.offers.get(part_ref, ())

    def default_offer(self, part_ref: str) -> SupplierOffer | None:
        candidates = self.offers_for(part_ref)
        for offer in candidates:
            if offer.is_default:
                return offer
        return candidates[0] if candidates else None

    def offer(self, part_ref: str, supplier_id: str) -> SupplierOffer | None:
        for candidate in self.offers_for(part_ref):
            if candidate.supplier_id == supplier_id:
                return candidate
        return None

    def default_plant(self, supplier_id: str) -> Plant | None:
        candidates = self.plants.get(supplier_id, ())
        for plant in candidates:
            if plant.is_default:
                return plant
        return candidates[0] if candidates else None

    def plant(self, supplier_id: str, plant_id: str) -> Plant | None:
        for candidate in self.plants.get(supplier_id, ()):
            if candidate.plant_id == plant_id:
                return candidate
        return None


@dataclass(frozen=True)
class ScenarioParameter:
    part_ref: str
    scope: Scope = "part"
    path: str | None = None
    supplier_id: str | None = None
    plant_id: str | None = None
    price_override: Decimal | None = None
    price_override_justification: str | None = None
    labour_minutes: Decimal | None = None
    purchase_currency: str | None = None

    @property
    def touches_purchase(self) -> bool:
        return any(
            value is not None
            for value in (
                self.supplier_id, self.plant_id, self.price_override,
                self.purchase_currency,
            )
        )


@dataclass(frozen=True)
class Scenario:
    id: str
    bom_version: str
    display_currency: str
    labour_rate: Decimal
    active_rules: frozenset[str] = field(
        default_factory=lambda: frozenset({"labour"})
    )
    parameters: Sequence[ScenarioParameter] = ()
    name: str = ""
    #: Le snapshot de calcul dont le scénario est reparti (ADR-0014). Une
    #: trace, pas un lien vivant : le scénario reste librement modifiable.
    derived_from: str | None = None
    #: Compter les pièces de rechange livrées avec le véhicule (SAV) en plus
    #: des pièces montées. Sans effet sur une nomenclature sans SAV.
    include_after_sales: bool = False

    def __post_init__(self) -> None:
        # Une copie peut partager des valeurs immuables, jamais les collections
        # modifiables que l'appelant a utilisées pour construire le scénario.
        # Les paramètres sont un jeu de cibles, sans ordre métier. Le même
        # ordre canonique en mémoire et en base rend l'aller-retour comparable.
        parameters = sorted(
            self.parameters, key=lambda p: (p.part_ref, p.path or "", p.scope),
        )
        object.__setattr__(self, "parameters", tuple(parameters))
        object.__setattr__(self, "active_rules", frozenset(self.active_rules))

    def parameter_for(
        self, part_ref: str, path: str | None = None
    ) -> ScenarioParameter | None:
        """Résout la portée pièce, puis la surcharge exacte de chemin.

        Un paramètre de chemin est une cible complète : s'il existe, il gagne
        sur celui de portée pièce. Ses champs absents reprennent donc les
        valeurs par défaut du catalogue, pas celles d'une autre cible.
        """
        part = next(
            (
                parameter
                for parameter in self.parameters
                if parameter.part_ref == part_ref and parameter.scope == "part"
            ),
            None,
        )
        if path is not None:
            specific = next(
                (
                    parameter
                    for parameter in self.parameters
                    if parameter.part_ref == part_ref
                    and parameter.scope == "path"
                    and parameter.path == path
                ),
                None,
            )
            if specific is not None:
                return specific
        return part
