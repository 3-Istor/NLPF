"""Point d'entrée de l'API.

C'est ici, et seulement ici, qu'on câble les adaptateurs concrets aux ports.
Le reste du code ne sait pas qu'il existe un Postgres (ADR-0004).

    uvicorn carcost.infrastructure.api.main:app --port 8000
"""

from __future__ import annotations

import os

from ..postgres_bom_repository import PostgresBomRepository
from .app import create_app

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")

app = create_app(PostgresBomRepository(DSN))
