"""À quels marchés le prix d'une pièce est-il exposé ?

Chaque pièce achetée reçoit un **profil** (câble, acier, batterie…) et le profil
donne des poids sur huit indices de marché. L'API de prix simulée en tire la
variation du prix : `facteur = 1 + Σ poids × variation de l'indice`.

Le profil est calculé ici, une fois, à la génération du jeu de données, et
écrit dans le catalogue. L'API ne devine rien à l'exécution : un classement qui
change doit se voir dans un diff du catalogue, pas dans un comportement.

Le change n'est **pas** un poids : il dépend de la devise du fournisseur, pas
de la matière. L'API l'applique séparément (prix GBP d'un fournisseur
britannique, puis conversion au cours simulé du jour).

Profils et poids repris de la PR #6, synthétiques. La somme des poids vaut 1.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

INDEX_NAMES = (
    "cuivre", "aluminium", "acier", "lithium", "nickel",
    "semi_conducteurs", "energie", "transport",
)

# Mêmes proportions que la PR #6, une fois retirée la part du change.
PROFILE_WEIGHTS: dict[str, tuple[str, ...]] = {
    "cable":       ("0.70", "0",    "0",    "0",    "0",    "0",    "0.18", "0.12"),
    "aluminium":   ("0",    "0.62", "0",    "0",    "0",    "0",    "0.25", "0.13"),
    "steel":       ("0",    "0",    "0.62", "0",    "0",    "0",    "0.25", "0.13"),
    "battery":     ("0.11", "0.11", "0",    "0.28", "0.22", "0.17", "0.06", "0.05"),
    "electronics": ("0.12", "0",    "0",    "0",    "0",    "0.65", "0.12", "0.11"),
    "motor":       ("0.28", "0.17", "0.11", "0",    "0",    "0.28", "0.11", "0.05"),
    "rubber":      ("0",    "0",    "0.12", "0",    "0",    "0",    "0.63", "0.25"),
    "composite":   ("0",    "0.14", "0",    "0",    "0",    "0",    "0.65", "0.21"),
    "default":     ("0",    "0",    "0.27", "0",    "0",    "0",    "0.46", "0.27"),
}

# L'ordre compte : une fixation reste une fixation, même si elle nomme l'organe
# qu'elle fixe ; une huile reste un fluide, même « de boîte ».
RULES = tuple(
    (profile, re.compile(pattern))
    for profile, pattern in (
        ("default", r"^(?:huile|ldr|refrigerant|liquide|fluide|essence|graisse)\b"),
        ("steel", r"\b(?:vis|visserie|boulons?|ecrous?|rondelles?|goujons?|rivets?|"
                  r"colliers?|agrafes?|clips?|fixations?)\b"),
        ("cable", r"\b(?:cables?|faisceaux?|wiring|harness|connecteurs?)\b"),
        ("battery", r"\b(?:batterie hv|pack (?:batterie|hv)|(?:modules?|cellules?) "
                    r"(?:de )?batterie|cellules?)\b"),
        ("electronics", r"\b(?:ecu|tcu|vcu|bcm|bms|adas|capteurs?|sensors?|electronique|"
                        r"radars?|cameras?|calculateurs?|tpms|chargeurs?|obc|pdu|"
                        r"contacteurs?|filtre emi|antennes?|ecran|afficheur|logiciels?|"
                        r"mechatronic|amplificateur|module)\b"),
        ("motor", r"\b(?:moteurs? electriques?|electric motors?|edu|emotor|inverters?|"
                  r"onduleurs?|demarreurs?|alternateurs?|moteur essuie)\b"),
        ("aluminium", r"\b(?:aluminium|aluminum|jantes?|radiateurs?|condenseur|"
                      r"echangeurs?|culasses?|bloc cylindres|carter|refroidisseur)\b"),
        ("steel", r"\b(?:acier|steel|chassis|sous cadres?|supports?|berceaux?|triangles?|"
                  r"biellettes?|bras|reducteurs?|pignons?|engrenages?|vilebrequin|"
                  r"pistons?|bielles?|arbres?|cames|soupapes?|ressorts?|amortisseurs?|"
                  r"barre|disques?|etriers?|collecteur|catalyseurs?|silencieux|"
                  r"downpipe|turbo\w*|embrayages?|demi arbre|joints? homocinetiques?|"
                  r"cremaillere|colonne)\b"),
        ("rubber", r"\b(?:pneus?|pneumatiques?|caoutchouc|rubber|tires?|tyres?|durites?|"
                   r"joints?|silentblocs?|soufflets?)\b"),
        ("composite", r"\b(?:carbone|carbon|composites?|carrosserie|monocoque|ailes?|"
                      r"capot|pare chocs|portes?|cloisons?|crash box|renforts?|"
                      r"panneaux?|diffuseur|aileron|doublure|bas de caisse|coques?|"
                      r"planche|garnitures?|habillages?)\b"),
    )
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def classify(name: str, description: str = "") -> str:
    """Le libellé prime sur la description : « Cloison avant | Carbone » est
    classée par son libellé si celui-ci suffit, par la description sinon."""
    for text in (name, description):
        normalized = normalize(text)
        for profile, pattern in RULES:
            if pattern.search(normalized):
                return profile
    return "default"


def weights(profile: str) -> dict[str, str]:
    """Les poids non nuls du profil, en chaînes (le catalogue est du texte)."""
    values = dict(zip(INDEX_NAMES, PROFILE_WEIGHTS[profile]))
    return {name: value for name, value in values.items() if Decimal(value)}


def _check_profiles() -> None:
    for profile, values in PROFILE_WEIGHTS.items():
        if len(values) != len(INDEX_NAMES):
            raise ValueError(f"profil {profile} : {len(values)} poids")
        if sum(Decimal(v) for v in values) != 1:
            raise ValueError(f"profil {profile} : la somme des poids n'est pas 1")


_check_profiles()


# ------------------------------------------------------------------ historique
#
# Les bornes annuelles du catalogue (`year_min`, `year_max`) sont celles que
# l'API simulée parcourra réellement : on les calcule depuis le même historique
# d'indices, jour par jour, au lieu de les tirer au hasard.

FX_INDEX = "GBP_EUR"


def load_indices(path) -> dict[str, list[Decimal]]:
    import json

    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        name: [Decimal(value) for value in values]
        for name, values in document["indices"].items()
    }


def daily_factors(drivers: dict[str, str], indices: dict[str, list[Decimal]]) -> list[Decimal]:
    """Le facteur de prix de chaque jour : 1 + Σ poids × variation de l'indice."""
    days = len(next(iter(indices.values())))
    return [
        1 + sum(
            (Decimal(w) * (indices[name][day] / indices[name][0] - 1) for name, w in drivers.items()),
            Decimal(0),
        )
        for day in range(days)
    ]


def fx_ratios(indices: dict[str, list[Decimal]]) -> list[Decimal]:
    """Variation du cours GBP→EUR depuis le premier jour."""
    series = indices[FX_INDEX]
    return [value / series[0] for value in series]
