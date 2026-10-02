"""Émet le script de chargement du jeu de données sur la sortie standard.

    python -m carcost.infrastructure seeds | psql ...

Toutes les nomenclatures du dossier sont émises : le Multipla à la racine, puis
chaque Valhalla de `seeds/valhalla/`. Chacune dans sa transaction.

Le script n'est émis que si **tous** les jeux passent leurs contrôles : un
fichier refusé ne produit rien, et rien n'entre en base.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .seed_loader import SeedRejected, build_load_script, read_seeds, seed_directories


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    seeds_dir = Path(arguments[0]) if arguments else Path("seeds")

    try:
        scripts = [
            build_load_script(**read_seeds(directory))
            for directory in seed_directories(seeds_dir)
        ]
    except SeedRejected as rejection:
        print(f"jeu de données refusé : {rejection}", file=sys.stderr)
        return 1

    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdout.write("\n".join(scripts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
