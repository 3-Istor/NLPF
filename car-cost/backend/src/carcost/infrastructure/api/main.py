"""Point d'entrée de l'API.

C'est ici, et seulement ici, qu'on câble les adaptateurs concrets aux ports.
Le reste du code ne sait pas qu'il existe un Postgres (ADR-0004).

    uvicorn carcost.infrastructure.api.main:app --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

from ..cached_bom_repository import CachedBomRepository
from ..postgres.bom import PostgresBomRepository
from ..postgres.calculations import PostgresCalculationRepository
from ..postgres.scenarios import PostgresScenarioRepository
from ..postgres.snapshots import PostgresPriceSnapshotRepository
from ..postgres.sourcing import PostgresSourcingRepository
from .app import Repositories, create_app
from ..price_data import DEFAULT_BOM_DIR

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")

PRICE_BOM_DIR = Path(os.environ.get("CARCOST_PRICE_BOM_DIR", str(DEFAULT_BOM_DIR)))

app = create_app(
    Repositories(
        bom=CachedBomRepository(PostgresBomRepository(DSN)),
        sourcing=PostgresSourcingRepository(DSN),
        snapshots=PostgresPriceSnapshotRepository(DSN),
        scenarios=PostgresScenarioRepository(DSN),
        calculations=PostgresCalculationRepository(DSN),
    ),
    price_bom_dir=PRICE_BOM_DIR,
)
