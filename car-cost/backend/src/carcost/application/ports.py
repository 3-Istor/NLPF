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


class PriceSource(Protocol):
    def fetch(
        self, refs: Sequence[str], currency: str
    ) -> Sequence[Quote]:  # pragma: no cover - contrat
        ...


class BomVersionNotFound(Exception):
    """Version de nomenclature inconnue."""


class BomVersionNotValidated(Exception):
    """La version n'a pas passé ses contrôles d'intégrité.

    Tant que `validated_at` est nul, rien ne se lit et rien ne se calcule
    dessus : un graphe dont on n'a pas prouvé l'acyclicité ne doit pas servir.
    """


class BomRepository(Protocol):
    def load(self, version: str):  # pragma: no cover - contrat
        """Renvoie la nomenclature complète d'une version validée."""
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


class PriceSnapshotRepository(Protocol):
    def latest(self):  # pragma: no cover - contrat
        """Le dernier snapshot pris, même périmé — ou None s'il n'y en a aucun."""
        ...

    def list_all(self):  # pragma: no cover - contrat
        """Liste les snapshots du plus récent au plus ancien."""
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
