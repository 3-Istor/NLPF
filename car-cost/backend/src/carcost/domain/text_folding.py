"""Le pliage du texte de recherche : sans accents, sans casse.

Règle partagée avec le front (`backend/tests/fold_cases.json` est lue par les
deux côtés) : deux implémentations qui divergent feraient trouver une pièce à
l'écran et pas à l'API, ou l'inverse.
"""

from __future__ import annotations

import unicodedata


def fold(text: str) -> str:
    """NFKD, sans les marques (catégorie `Mn`), puis `casefold`."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return stripped.casefold()
