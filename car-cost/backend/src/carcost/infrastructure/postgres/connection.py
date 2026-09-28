"""Une connexion par opération, ouverte et refermée dans la même méthode.

Il n'y a pas de pool : la nomenclature est gardée en mémoire (ADR-0012), et ce
qui reste — scénarios, calculs, snapshots — se compte en requêtes par action
de l'utilisateur, pas par ligne d'arbre.
"""

from __future__ import annotations

import psycopg


class PostgresRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def _connect(self):
        return psycopg.connect(self.dsn)
