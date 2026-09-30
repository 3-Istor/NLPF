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
from ...application.tree_view import with_costs
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
from .snapshot_routes import register_snapshot_routes

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

    @app.get("/api/v1/bom/{version}/root")
    def read_root(version: str, calculation_id: str | None = Query(None)):
        bom = repository.load(version)
        return _render(repositories, bom, (root_node(bom),), calculation_id)[0]

    @app.get("/api/v1/bom/{version}/children")
    def read_children(
        version: str,
        path: str = Query(..., description="Le nœud à déplier, chemin complet"),
        calculation_id: str | None = Query(
            None, description="Enrichit chaque ligne des chiffres de ce calcul"
        ),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        # Aucun paramètre de profondeur : le dépliage se fait nœud par nœud, et
        # le navigateur ne doit jamais pouvoir demander le graphe entier.
        bom = repository.load(version)
        page = children_of_path(bom, path, limit=limit, offset=offset)
        return {
            "path": path,
            "items": _render(repositories, bom, page.items, calculation_id),
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

    @app.get("/api/v1/bom/{version}/parts/{part_ref}")
    def read_part(version: str, part_ref: str):
        """La fiche d'une pièce, et ses options de sourcing si elle est achetée.

        Sur un ensemble fabriqué, la clé `suppliers` est **absente** — pas vide.
        Une liste vide inviterait l'écran à afficher un sélecteur sans options ;
        l'absence lui dit qu'il n'y a pas de fournisseur à choisir (ADR-0008).
        """
        bom = repository.load(version)
        part = bom.parts.get(part_ref)
        if part is None:
            raise PathNotFound(f"référence inconnue : {part_ref}")

        payload = {
            "part_ref": part.ref,
            "label": part.label,
            "system": part.system,
            "unit": part.unit,
            "valuation_mode": part.valuation_mode.value,
            "labour_minutes": (
                str(part.labour_minutes) if part.labour_minutes is not None else None
            ),
            "occurrence_count": where_used(bom, part_ref, limit=1).total,
        }
        if part.is_purchased and repositories.sourcing is not None:
            sourcing = repositories.sourcing.load(version)
            payload["suppliers"] = [
                {
                    "supplier_id": offer.supplier_id,
                    "name": offer.name or offer.supplier_id,
                    "price_multiplier": str(offer.price_multiplier),
                    "is_default": offer.is_default,
                    "plants": [
                        {
                            "plant_id": plant.plant_id,
                            "label": plant.label or plant.plant_id,
                            "origin_country": plant.origin_country,
                            "price_coefficient": str(plant.price_coefficient),
                            "lead_time_days": plant.lead_time_days,
                            "is_default": plant.is_default,
                        }
                        for plant in sourcing.plants.get(offer.supplier_id, ())
                    ],
                }
                for offer in sourcing.offers_for(part_ref)
            ]
        return payload

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


def _render(repositories, bom, nodes, calculation_id: str | None) -> list[dict]:
    """Les lignes, avec ou sans les chiffres d'un calcul.

    Sans `calculation_id`, aucun champ monétaire n'est renvoyé — pas même à
    zéro : un zéro se lit comme un prix.
    """
    if calculation_id is None:
        return [_node_payload(node) for node in nodes]

    calculation = repositories.calculations.get(calculation_id)
    scenario = repositories.scenarios.get(calculation.scenario_id)
    return [
        _costed_payload(costed, calculation.display_currency)
        for costed in with_costs(bom, tuple(nodes), calculation, scenario)
    ]


def _costed_payload(costed, currency: str) -> dict:
    payload = _node_payload(costed.node)
    payload.update(
        {
            "quantity_on_path": str(costed.quantity_on_path),
            "unit_cost": _money(costed.unit_cost, currency),
            "own_unit_cost": _money(costed.own_unit_cost, currency),
            # Ce que pèse cette occurrence, enfants compris. Ne se somme pas
            # entre niveaux : un parent contient déjà ses enfants.
            "rolled_up_contribution": _money(costed.rolled_up_contribution, currency),
            # La seule grandeur qui se somme au total.
            "own_contribution": _money(costed.own_contribution, currency),
            "price_status": costed.price_status,
            "is_modified": costed.is_modified,
            "has_modified_descendant": costed.has_modified_descendant,
        }
    )
    return payload


def _money(amount: Decimal | None, currency: str) -> dict | None:
    if amount is None:
        return None
    return {"amount": str(amount), "currency": currency}


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
