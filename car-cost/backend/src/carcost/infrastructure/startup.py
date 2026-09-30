"""Prépare une installation locale sans écraser les données déjà enregistrées."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg

from .seed_loader import build_load_script, read_seeds
from .snapshot_cli import DEFAULT_DSN, main as take_first_snapshot


def initialize(dsn: str, seeds_dir: Path = Path("seeds")) -> None:
    seeds = read_seeds(seeds_dir)
    version = seeds["metadata"]["bom_version_id"]
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            "SELECT validated_at FROM bom_version WHERE id = %s", (version,)
        ).fetchone()

    if row is None:
        # La validation précède psql : un jeu refusé ne peut écrire en base.
        script = build_load_script(**seeds)
        subprocess.run(
            ["psql", "--dbname", dsn, "-v", "ON_ERROR_STOP=1", "-q"],
            input=script, text=True, check=True,
        )
        print(f"nomenclature synthétique {version} chargée", flush=True)
    elif row[0] is None:
        raise RuntimeError(
            f"la nomenclature {version} existe mais n'est pas validée ; "
            "intervention nécessaire, aucune donnée n'a été remplacée"
        )
    else:
        print(f"nomenclature {version} conservée", flush=True)

    with psycopg.connect(dsn) as connection:
        snapshot = connection.execute("SELECT id FROM price_snapshot LIMIT 1").fetchone()
    if snapshot is None:
        if take_first_snapshot(["--dsn", dsn, "--bom-version", version]) != 0:
            raise RuntimeError("impossible de prendre le premier snapshot de prix")
    else:
        print("snapshots de prix conservés", flush=True)


def main() -> int:
    try:
        initialize(os.environ.get("CARCOST_DSN", DEFAULT_DSN))
    except Exception as error:
        # Ne pas exposer le DSN dans les logs en cas d'échec de psql.
        message = (
            "chargement SQL refusé"
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        print(f"initialisation refusée : {message}", file=sys.stderr, flush=True)
        return 1
    command = sys.argv[1:]
    if not command:
        print("initialisation terminée", flush=True)
        return 0
    # Le serveur reçoit directement les signaux d'arrêt de Docker.
    os.execvp(command[0], command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
