"""Point d'entrée de l'API.

C'est ici, et seulement ici, qu'on câble les adaptateurs concrets aux ports.
Le reste du code ne sait pas qu'il existe un Postgres (ADR-0004).

    uvicorn carcost.infrastructure.api.main:app --port 8000
"""

from __future__ import annotations

import os

from ..cached_bom_repository import CachedBomRepository
from ..postgres.bom import PostgresBomRepository
from ..postgres.calculation_snapshots import PostgresCalculationSnapshotRepository
from ..postgres.calculations import PostgresCalculationRepository
from ..postgres.scenarios import PostgresScenarioRepository
from ..postgres.snapshots import PostgresPriceSnapshotRepository
from ..postgres.sourcing import PostgresSourcingRepository
from ..http_price_source import HttpPriceSource
from .app import Repositories, create_app

DSN = os.environ.get("CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor")

app = create_app(
    Repositories(
        bom=CachedBomRepository(PostgresBomRepository(DSN)),
        sourcing=PostgresSourcingRepository(DSN),
        snapshots=PostgresPriceSnapshotRepository(DSN),
        scenarios=PostgresScenarioRepository(DSN),
        calculations=PostgresCalculationRepository(DSN),
        calculation_snapshots=PostgresCalculationSnapshotRepository(DSN),
        prices=HttpPriceSource(
            os.environ.get("CARCOST_PRICE_API", "http://127.0.0.1:8099"),
            timeout_seconds=float(os.environ.get("CARCOST_PRICE_TIMEOUT", "5")),
        ),
    )
)
