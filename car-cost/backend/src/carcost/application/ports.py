"""Ce que l'application attend du monde extérieur.

Un port dit ce dont on a besoin, pas comment on l'obtient : le client HTTP, le
fichier de catalogue ou le double de test sont interchangeables, et aucun n'est
nommé ici.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Protocol, Sequence


class PriceSourceError(Exception):
    """L'appel n'a pas abouti. Jamais propagée telle quelle jusqu'à l'écran."""


class PriceSourceTimeout(PriceSourceError):
    """La source n'a pas répondu dans le temps imparti (mode de panne P1)."""


@dataclass(frozen=True)
class Quote:
    """Ce que la source a répondu pour une pièce, avant tout jugement.

    `price` vaut None quand la réponse est inexploitable — non numérique,
    devise inconnue. On garde `raw` pour pouvoir dire dans le journal ce qui a
    été refusé, et pas seulement qu'on a refusé quelque chose.
    """

    part_ref: str
    price: Decimal | None
    raw: str
    reason: str | None = None


class PriceNotQuoted(Exception):
    """La source ne cote pas cette pièce dans cette devise."""


@dataclass(frozen=True)
class PricePoint:
    day: str
    #: Prix ramené à l'unité, comme une cotation (`per` déjà divisé).
    price: Decimal


@dataclass(frozen=True)
class PriceHistory:
    """L'année de marché d'une pièce, telle que la source la simule."""

    part_ref: str
    currency: str
    unit: str
    reference: Decimal
    points: tuple[PricePoint, ...]
    now_at: str
    now_price: Decimal
    profile: str | None = None
    drivers: Mapping[str, Decimal] = None  # type: ignore[assignment]
    origin_currency: str | None = None


class PriceSource(Protocol):
    def fetch(
        self, refs: Sequence[str], currency: str
    ) -> Sequence[Quote]:  # pragma: no cover - contrat
        ...

    def history(
        self, ref: str, currency: str
    ) -> PriceHistory:  # pragma: no cover - contrat
        """Lève PriceNotQuoted si la pièce n'est pas cotée, PriceSourceError
        si la source ne répond pas."""
        ...


class BomVersionNotFound(Exception):
    """Version de nomenclature inconnue."""


class BomVersionNotValidated(Exception):
    """La version n'a pas passé ses contrôles d'intégrité.

    Tant que `validated_at` est nul, rien ne se lit et rien ne se calcule
    dessus : un graphe dont on n'a pas prouvé l'acyclicité ne doit pas servir.
    """


@dataclass(frozen=True)
class BomVersionSummary:
    """Ce qu'il faut pour choisir une version, sans charger son graphe."""

    id: str
    label: str
    root_part_ref: str
    part_count: int
    edge_count: int
    #: None tant que la version n'a pas passé ses contrôles : elle est listée,
    #: mais ni lue ni calculée.
    validated_at: datetime | None
    is_synthetic: bool
    #: Taux horaire proposé à la création d'un scénario sur cette version.
    reference_labour_rate: Decimal | None = None
    #: Version dont celle-ci est la variante (import d'un modèle 3D, ADR-0017).
    parent_version_id: str | None = None


class BomRepository(Protocol):
    def load(self, version: str):  # pragma: no cover - contrat
        """Renvoie la nomenclature complète d'une version validée."""
        ...

    def versions(self) -> Sequence[BomVersionSummary]:  # pragma: no cover
        """Toutes les versions, validées ou non, la plus récente d'abord."""
        ...


class SourcingRepository(Protocol):
    def load(self, bom_version: str):  # pragma: no cover - contrat
        """Qui peut fournir quoi, et depuis quelles usines."""
        ...


class PriceSnapshotNotFound(KeyError):
    """Snapshot inconnu."""


@dataclass(frozen=True)
class QuarantineRecord:
    """Une valeur refusée, telle que le journal la conserve.

    `rejected_value` reste du texte : ce que l'API a renvoyé n'était pas
    forcément un nombre, et c'est précisément ce qu'on veut pouvoir montrer.
    """

    part_ref: str
    currency: str
    rejected_value: str
    reason: str
    #: Ce qui a été retenu à la place, ou None : la pièce est alors sans prix.
    replacement: Decimal | None
    replacement_from_snapshot: str | None
    detected_at: datetime


@dataclass(frozen=True)
class FrozenPrice:
    """Le prix d'une pièce dans un snapshot enregistré."""

    snapshot_id: str
    taken_at: datetime
    price: Decimal
    #: API, ou FALLBACK quand le prix venait du snapshot précédent.
    origin: str


class PriceSnapshotRepository(Protocol):
    def history_of(
        self, part_ref: str, bom_version: str, currency: str, limit: int = 20
    ) -> Sequence[FrozenPrice]:  # pragma: no cover - contrat
        """Les prix figés d'une pièce, du plus récent au plus ancien."""
        ...

    def latest(self, bom_version: str | None = None):  # pragma: no cover - contrat
        """Le dernier snapshot pris pour cette nomenclature, même périmé — ou None.

        À défaut, le dernier snapshot pris avant que les snapshots ne portent
        leur nomenclature (ADR-0015). `None` : le dernier, toutes confondues.
        """
        ...

    def list_all(self, bom_version: str | None = None):  # pragma: no cover - contrat
        """Liste les snapshots du plus récent au plus ancien, de cette
        nomenclature (et les anciens, sans nomenclature) si elle est donnée."""
        ...

    def get(self, snapshot_id: str):  # pragma: no cover - contrat
        """Lève PriceSnapshotNotFound si l'identifiant est inconnu."""
        ...

    def save(
        self, snapshot, quarantined=(), previous_id: str | None = None
    ) -> None:  # pragma: no cover - contrat
        """Écrit un snapshot et son journal de quarantaine.

        Ne le modifie jamais : un nouveau est un nouveau.
        """
        ...

    def quarantine_of(
        self, snapshot_id: str
    ) -> Sequence[QuarantineRecord]:  # pragma: no cover - contrat
        """Le journal d'un snapshot, vide s'il est sain.

        Lève PriceSnapshotNotFound si l'identifiant est inconnu : un journal
        vide ne doit pas pouvoir se lire comme « tout allait bien » pour un
        snapshot qui n'existe pas.
        """
        ...


class ScenarioNotFound(Exception):
    """Scénario inconnu."""


class ScenarioRepository(Protocol):
    def set_after_sales(
        self, scenario_id: str, include: bool
    ) -> None:  # pragma: no cover - contrat
        """Bascule le SAV. Lève ScenarioNotFound si le scénario n'existe pas."""
        ...

    def set_labour_rate(
        self, scenario_id: str, rate: Decimal
    ) -> None:  # pragma: no cover - contrat
        """Change le taux horaire. Lève ScenarioNotFound si le scénario n'existe pas."""
        ...

    def create(self, scenario) -> None:  # pragma: no cover - contrat
        """Insère le scénario et tous ses paramètres dans une seule transaction."""
        ...

    def get(self, scenario_id: str):  # pragma: no cover - contrat
        ...

    def list_all(self):  # pragma: no cover - contrat
        """Liste les scénarios du plus récent au plus ancien."""
        ...

    def delete(self, scenario_id: str) -> None:  # pragma: no cover - contrat
        """Supprime le scénario et ses données dépendantes."""
        ...

    def parameter_ids(self, scenario_id: str):  # pragma: no cover - contrat
        """Associe chaque cible de paramètre à son identifiant persistant."""
        ...

    def put_parameter(self, scenario_id: str, parameter) -> str:  # pragma: no cover
        """Pose ou remplace le paramètre visant cette cible, et rend son id."""
        ...

    def delete_parameter(self, scenario_id: str, parameter_id: str) -> None:
        ...  # pragma: no cover - contrat


class CalculationNotFound(Exception):
    """Calcul inconnu."""


class CalculationRepository(Protocol):
    def save(self, calculation) -> None:  # pragma: no cover - contrat
        ...

    def get(self, calculation_id: str):  # pragma: no cover - contrat
        ...

    def latest_for(self, scenario_id: str):  # pragma: no cover - contrat
        """Le dernier calcul de ce scénario, ou None."""
        ...


class CalculationSnapshotNotFound(Exception):
    """Snapshot de calcul inconnu."""


class SnapshotNameTaken(Exception):
    """Le nom est déjà pris dans cette version de nomenclature (ADR-0014).

    La comparaison se fait sans casse ni accents : « Référence » et
    « reference » désigneraient le même résultat retenu.
    """

    def __init__(self, name: str, existing_id: str):
        super().__init__(f"le nom « {name} » est déjà pris ({existing_id})")
        self.name = name
        self.existing_id = existing_id


class CalculationSnapshotRepository(Protocol):
    """Pas de suppression : un snapshot de calcul ne disparaît pas."""

    def save(self, snapshot) -> None:  # pragma: no cover - contrat
        """Lève SnapshotNameTaken si la clé du nom est prise dans la version."""
        ...

    def get(self, snapshot_id: str):  # pragma: no cover - contrat
        """Lève CalculationSnapshotNotFound si l'identifiant est inconnu."""
        ...

    def list_for(self, bom_version: str):  # pragma: no cover - contrat
        """Les snapshots d'une version, du plus récent au plus ancien."""
        ...

    def for_scenario(self, scenario_id: str):  # pragma: no cover - contrat
        """Les snapshots figés depuis ce scénario."""
        ...

    def rename(
        self, snapshot_id: str, name: str, renamed_at: datetime
    ) -> None:  # pragma: no cover - contrat
        """Change le nom seul et trace le renommage ; SnapshotNameTaken."""
        ...

    def name_history(
        self, snapshot_id: str
    ) -> Sequence[tuple[str, datetime]]:  # pragma: no cover - contrat
        """Les noms successifs depuis la création, dans l'ordre."""
        ...
