"""L'application FastAPI : câblage des dépôts, format des erreurs, routes.

Les routes vivent par fonctionnalité dans les modules `*_routes` ; ce module ne
fait que les réunir et traduire les exceptions des cas d'usage en codes nommés
(docs/api.md §1.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI, Request

from ...application.browse_bom import PathNotFound
from ...application.ports import (
    BomRepository,
    BomVersionNotFound,
    BomVersionNotValidated,
    CalculationNotFound,
    CalculationRepository,
    CalculationSnapshotRepository,
    PriceNotQuoted,
    PriceSnapshotRepository,
    PriceSource,
    PriceSourceError,
    ScenarioNotFound,
    ScenarioRepository,
    SourcingRepository,
)
from ...application.take_snapshot import NoPriceAvailable
from ..live_calculations import LiveCalculations, WithLiveCalculations
from .bom_routes import register_bom_routes
from .calculation_routes import register_calculation_routes
from .calculation_snapshot_routes import register_calculation_snapshot_routes
from .errors import error_response
from .snapshot_routes import register_snapshot_routes

@dataclass
class Repositories:
    """Les adaptateurs concrets, réunis en un point de câblage.

    C'est le seul endroit qui sait qu'il existe un Postgres et une API de prix ;
    ni le domaine ni les cas d'usage ne les nomment (ADR-0004).
    """

    bom: BomRepository
    sourcing: SourcingRepository | None = None
    snapshots: PriceSnapshotRepository | None = None
    scenarios: ScenarioRepository | None = None
    calculations: CalculationRepository | None = None
    calculation_snapshots: CalculationSnapshotRepository | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    #: L'API de prix, interrogée en direct : mode direct, figer les prix,
    #: historique d'une pièce. None : ces routes répondent qu'elle manque.
    prices: PriceSource | None = None
    #: Les calculs en direct, jamais enregistrés (ADR-0015), gardés le temps
    #: que l'arbre lise leurs lignes.
    live: LiveCalculations = field(default_factory=LiveCalculations)


def create_app(repositories: Repositories) -> FastAPI:
    if repositories.calculations is not None and not isinstance(
        repositories.calculations, WithLiveCalculations
    ):
        repositories.calculations = WithLiveCalculations(
            repositories.calculations, repositories.live
        )

    app = FastAPI(
        title="3istor",
        description=(
            "Coût de fabrication explicable d'un véhicule. Les données servies "
            "sont plausibles mais synthétiques."
        ),
        version="0.1.0",
    )

    @app.exception_handler(PriceSourceError)
    async def _price_source(_: Request, error: PriceSourceError):
        return _error(503, "PRICE_SOURCE_UNAVAILABLE", f"API de prix indisponible : {error}")

    @app.exception_handler(NoPriceAvailable)
    async def _no_price(_: Request, error: NoPriceAvailable):
        return _error(503, "PRICE_SOURCE_UNAVAILABLE", str(error))

    @app.exception_handler(PriceNotQuoted)
    async def _not_quoted(_: Request, error: PriceNotQuoted):
        return _error(404, "PRICE_NOT_QUOTED", str(error))

    @app.get("/health")
    def health():
        """Sonde de vie ; Compose attend aussi la fin de l’initialisation."""
        return {"status": "ok"}

    @app.exception_handler(BomVersionNotFound)
    async def _version_not_found(_: Request, error: BomVersionNotFound):
        return _error(404, "BOM_VERSION_NOT_FOUND", str(error))

    @app.exception_handler(BomVersionNotValidated)
    async def _version_not_validated(_: Request, error: BomVersionNotValidated):
        return _error(
            409,
            "BOM_VERSION_NOT_VALIDATED",
            f"la version {error} n'a pas passé ses contrôles d'intégrité ; "
            f"aucun calcul n'est autorisé dessus",
        )

    @app.exception_handler(PathNotFound)
    async def _path_not_found(_: Request, error: PathNotFound):
        return _error(404, "PATH_NOT_FOUND", str(error))

    @app.exception_handler(ScenarioNotFound)
    async def _scenario_not_found(_: Request, error: ScenarioNotFound):
        return _error(404, "SCENARIO_NOT_FOUND", str(error))

    @app.exception_handler(CalculationNotFound)
    async def _calculation_not_found(_: Request, error: CalculationNotFound):
        return _error(404, "CALCULATION_NOT_FOUND", str(error))

    register_calculation_routes(app, repositories)
    register_snapshot_routes(app, repositories)
    register_calculation_snapshot_routes(app, repositories)
    register_bom_routes(app, repositories)

    return app


def _error(status: int, code: str, message: str, details: dict | None = None):
    return error_response(status, code, message, details)
