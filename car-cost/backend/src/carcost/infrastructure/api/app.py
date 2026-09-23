"""Les routes de lecture du graphe.

Elles traduisent une requête HTTP en appel de cas d'usage, et le résultat en
JSON. Elles ne calculent rien : pas une quantité, pas un prix, pas un compte
d'emplois — tout cela vient de la couche application (ADR-0007).

Les nombres partent en **chaînes décimales** : un flottant JSON suffirait à
rendre la reproductibilité au centime indémontrable (ADR-0011).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from ...application.browse_bom import (
    PathNotFound,
    children_of_path,
    root_node,
    search_parts,
    where_used,
)
from ...application.ports import (
    BomRepository,
    BomVersionNotFound,
    BomVersionNotValidated,
    CalculationNotFound,
    CalculationRepository,
    PriceSnapshotRepository,
    ScenarioNotFound,
    ScenarioRepository,
    SourcingRepository,
)
from .calculation_routes import register_calculation_routes
from .errors import error_response

SCALE = Decimal("0.000001")


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
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def create_app(repositories: Repositories) -> FastAPI:
    repository = repositories.bom
    app = FastAPI(
        title="3istor",
        description=(
            "Coût de fabrication explicable d'un véhicule. Les données servies "
            "sont plausibles mais synthétiques."
        ),
        version="0.1.0",
    )

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

    @app.get("/api/v1/bom/{version}/root")
    def read_root(version: str):
        return _node_payload(root_node(repository.load(version)))

    @app.get("/api/v1/bom/{version}/children")
    def read_children(
        version: str,
        path: str = Query(..., description="Le nœud à déplier, chemin complet"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        # Aucun paramètre de profondeur : le dépliage se fait nœud par nœud, et
        # le navigateur ne doit jamais pouvoir demander le graphe entier.
        page = children_of_path(
            repository.load(version), path, limit=limit, offset=offset
        )
        return {
            "path": path,
            "items": [_node_payload(node) for node in page.items],
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
        }

    @app.get("/api/v1/bom/{version}/where-used")
    def read_where_used(
        version: str,
        part_ref: str = Query(...),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        page = where_used(repository.load(version), part_ref, limit=limit, offset=offset)
        return {
            "part_ref": part_ref,
            "occurrence_count": page.total,
            "items": [
                {
                    "path": occurrence.path,
                    "path_labels": list(occurrence.path_labels),
                    "quantity_on_path": _decimal(occurrence.quantity_on_path),
                }
                for occurrence in page.items
            ],
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
        }

    @app.get("/api/v1/bom/{version}/search")
    def read_search(
        version: str,
        q: str = Query(..., min_length=1),
        limit: int = Query(20, ge=1, le=100),
    ):
        hits = search_parts(repository.load(version), q, limit=limit)
        return {
            "items": [
                {
                    "part_ref": hit.part_ref,
                    "label": hit.label,
                    "system": hit.system,
                    "occurrence_count": hit.occurrence_count,
                    "paths": list(hit.paths),
                    "paths_truncated": hit.paths_truncated,
                }
                for hit in hits
            ]
        }

    return app


def _decimal(value: Decimal) -> str:
    return str(value.quantize(SCALE))


def _node_payload(node) -> dict:
    """Ce qu'une ligne d'arbre porte, sans les chiffres d'un calcul.

    Tant qu'aucun calcul n'a été demandé, aucun champ monétaire n'est renvoyé —
    pas même à zéro : un zéro se lit comme un prix.
    """
    return {
        "path": node.path,
        "part_ref": node.part_ref,
        "label": node.label,
        "system": node.system,
        "valuation_mode": node.valuation_mode,
        "unit": node.unit,
        "edge_quantity": _decimal(node.edge_quantity),
        "has_children": node.has_children,
        "child_count": node.child_count,
        "parent_count": node.parent_count,
        "occurrence_count": node.occurrence_count,
    }


def _error(status: int, code: str, message: str, details: dict | None = None):
    return error_response(status, code, message, details)
