"""L'état d'un total affiché, et la portée d'un paramètre.

Deux choses que l'écran doit dire et qu'il ne peut pas déduire seul : si les
totaux qu'il montre sont encore les bons, et ce que le réglage qu'on vient de
poser affecte réellement.
"""

from __future__ import annotations

from dataclasses import replace
from enum import Enum

from ..domain.prices import PriceSnapshot
from .run_calculation import input_digest
from .scenario import Scenario


class CalculationState(str, Enum):
    NEVER_RUN = "NEVER_RUN"
    UP_TO_DATE = "UP_TO_DATE"
    #: Les totaux affichés ne correspondent plus aux entrées courantes. Ils sont
    #: marqués obsolètes : afficher un ancien total comme s'il était frais est
    #: une faute, pas un détail d'ergonomie.
    PARAMETERS_CHANGED = "PARAMETERS_CHANGED"
    #: Aucun snapshot : rien ne peut être calculé, et on le dit.
    NO_PRICES = "NO_PRICES"


def state_of(
    scenario: Scenario,
    snapshot: PriceSnapshot | None,
    *,
    last_digest: str | None,
    last_snapshot_id: str | None = None,
) -> tuple[CalculationState, str | None]:
    """Compare l'empreinte des entrées courantes à celle du dernier calcul.

    La raison est renvoyée séparément parce que « tes paramètres ont changé » et
    « les prix ont changé » n'appellent pas la même réaction, même si les deux
    rendent le total obsolète.

    L'identifiant du snapshot utilisé par le dernier calcul est passé par
    l'appelant — il est sur la ligne de calcul. Le déduire de l'empreinte serait
    impossible, et le deviner donnerait une raison fausse un jour sur deux.
    """
    if snapshot is None:
        return CalculationState.NO_PRICES, None
    if last_digest is None:
        return CalculationState.NEVER_RUN, None

    if input_digest(scenario, snapshot) == last_digest:
        return CalculationState.UP_TO_DATE, None

    return CalculationState.PARAMETERS_CHANGED, _reason(
        scenario, snapshot, last_digest, last_snapshot_id
    )


def _reason(
    scenario: Scenario,
    snapshot: PriceSnapshot,
    last_digest: str,
    last_snapshot_id: str | None,
) -> str:
    """Les paramètres, rejoués avec l'ancien snapshot, retombent-ils sur
    l'ancienne empreinte ? Si oui, seuls les prix ont bougé."""
    if last_snapshot_id is None or last_snapshot_id == snapshot.id:
        return "parameters"

    as_before = replace(snapshot, id=last_snapshot_id)
    return "prices" if input_digest(scenario, as_before) == last_digest else "parameters"


SCOPE_LABELS = {
    "path": "S'applique à cette occurrence uniquement",
}


def scope_label(scope: str, *, occurrences: int) -> str:
    """La phrase que l'écran affiche à côté du réglage.

    Sans elle, l'utilisateur ne peut pas interpréter son propre résultat : il ne
    sait pas s'il vient de changer le fournisseur d'une vis ou de douze.
    """
    if scope == "path":
        return SCOPE_LABELS["path"]
    if scope == "part":
        if occurrences == 1:
            return "S'applique à l'unique occurrence de cette pièce"
        return f"S'applique aux {occurrences} occurrences de cette pièce"
    raise ValueError(f"portée inconnue : {scope}")
