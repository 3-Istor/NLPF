"""Le modèle 3D d'une version (ADR-0017 §5) : lecture seule, il s'écrit avec sa version."""

from __future__ import annotations

from ...application.ports import StoredModel
from .connection import PostgresRepository


class PostgresBodyModelRepository(PostgresRepository):
    def get(self, version: str) -> StoredModel | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT glb, sha256, source FROM bom_model WHERE bom_version_id = %s",
                (version,),
            ).fetchone()
        return None if row is None else StoredModel(version, bytes(row[0]), row[1], row[2])
