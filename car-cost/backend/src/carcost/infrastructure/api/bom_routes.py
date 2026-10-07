"""Les routes de lecture du graphe.

Elles traduisent une requête HTTP en appel de cas d'usage, et le résultat en
JSON. Elles ne calculent rien : pas une quantité, pas un prix, pas un compte
d'emplois — tout cela vient de la couche application (ADR-0007).

Les nombres partent en **chaînes décimales** : un flottant JSON suffirait à
rendre la reproductibilité au centime indémontrable (ADR-0011).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI, Query, Request

from ...application.browse_bom import (
    PathNotFound,
    children_of_path,
    root_node,
    search_parts,
    search_summary,
    where_used,
)
from ...application.freeze_calculation import frozen_scenario
from ...application.supplier_catalog import suppliers_of
from ...application.tree_view import with_costs
from .errors import error_response
from .price_source import price_source

SCALE = Decimal("0.000001")

_FROZEN = (
    "Snapshot de calcul ouvert : chiffres de son calcul figé, marques ●/○ "
    "d'après sa copie des réglages"
)


class CalculationSnapshotMismatch(ValueError):
    """`calculation_id` et `calculation_snapshot_id` désignent deux calculs."""


def register_bom_routes(app: FastAPI, repositories) -> None:
    repository = repositories.bom

    @app.exception_handler(CalculationSnapshotMismatch)
    async def _mismatch(_: Request, error: CalculationSnapshotMismatch):
        return error_response(422, "CALCULATION_SNAPSHOT_MISMATCH", str(error))

    @app.get("/api/v1/bom/versions")
    def read_versions():
        return {
            "items": [
                {
                    "id": summary.id,
                    "label": summary.label,
                    "root_part_ref": summary.root_part_ref,
                    "part_count": summary.part_count,
                    "edge_count": summary.edge_count,
                    "validated_at": (
                        summary.validated_at.isoformat()
                        if summary.validated_at
                        else None
                    ),
                    "is_synthetic": summary.is_synthetic,
                    "reference_labour_rate": (
                        str(summary.reference_labour_rate)
                        if summary.reference_labour_rate is not None
                        else None
                    ),
                    # Absente hors variante, comme `suppliers` sur un ensemble.
                    **(
                        {"parent_version_id": summary.parent_version_id}
                        if summary.parent_version_id
                        else {}
                    ),
                }
                for summary in repository.versions()
            ]
        }

    def _catalog(version: str):
        if repositories.sourcing is None:
            return ()
        return suppliers_of(repository.load(version), repositories.sourcing.load(version))

    @app.get("/api/v1/bom/{version}/suppliers")
    def read_suppliers(version: str):
        """Les fournisseurs qui vendent au moins une pièce de cette nomenclature."""
        return {
            "items": [
                {
                    "supplier_id": entry.supplier_id,
                    "name": entry.name,
                    "part_count": len(entry.parts),
                    "default_count": entry.default_count,
                    "plants": [_plant_payload(plant) for plant in entry.plants],
                }
                for entry in _catalog(version)
            ]
        }

    @app.get("/api/v1/bom/{version}/suppliers/{supplier_id}/parts")
    def read_supplier_parts(version: str, supplier_id: str):
        """Les pièces que ce fournisseur vend pour cette nomenclature.

        Le prix de référence est celui du dernier snapshot de la nomenclature,
        tel quel : le multiplicateur et l'usine s'y appliquent au calcul
        (ADR-0010), pas ici.
        """
        entry = next(
            (e for e in _catalog(version) if e.supplier_id == supplier_id), None
        )
        if entry is None:
            return error_response(
                404, "SUPPLIER_NOT_FOUND",
                f"{supplier_id} ne vend aucune pièce de {version}",
            )
        snapshot = (
            repositories.snapshots.latest(version)
            if repositories.snapshots is not None
            else None
        )
        return {
            "supplier_id": entry.supplier_id,
            "name": entry.name,
            "plants": [_plant_payload(plant) for plant in entry.plants],
            "price_snapshot": (
                {
                    "id": snapshot.id,
                    "taken_at": snapshot.taken_at.isoformat(),
                    "currency": snapshot.currency,
                }
                if snapshot
                else None
            ),
            "items": [
                {
                    "part_ref": part.part_ref,
                    "label": part.label,
                    "unit": part.unit,
                    "system": part.system,
                    "price_multiplier": str(part.price_multiplier),
                    "is_default": part.is_default,
                    "reference_price": (
                        {
                            "amount": str(snapshot.prices[part.part_ref]),
                            "currency": snapshot.currency,
                        }
                        if snapshot and part.part_ref in snapshot.prices
                        else None
                    ),
                }
                for part in entry.parts
            ],
        }

    @app.get("/api/v1/bom/{version}/parts/{part_ref}/price-history")
    def read_price_history(
        version: str,
        part_ref: str,
        currency: str = Query("EUR", description="Devise de la courbe."),
    ):
        """L'année de marché simulée d'une pièce achetée, et les prix figés.

        Les snapshots sont datés en temps réel, la courbe en temps simulé :
        on ne les place pas sur le même axe, on les donne à côté.
        """
        bom = repository.load(version)
        part = bom.parts.get(part_ref)
        if part is None:
            return error_response(404, "PART_NOT_FOUND", f"{part_ref} n'est pas dans {version}")
        if not part.is_purchased:
            return error_response(
                409, "PART_HAS_NO_PRICE",
                f"{part_ref} est fabriquée : son coût est celui de ses enfants (ADR-0008)",
            )
        history = price_source(repositories).history(part_ref, currency)
        frozen = (
            repositories.snapshots.history_of(part_ref, version, currency)
            if repositories.snapshots is not None
            else ()
        )
        return {
            "part_ref": part_ref,
            "label": part.label,
            "unit": part.unit,
            "currency": history.currency,
            "profile": history.profile,
            "drivers": {name: str(weight) for name, weight in (history.drivers or {}).items()},
            "origin_currency": history.origin_currency,
            "reference": str(history.reference),
            "points": [{"date": p.day, "price": str(p.price)} for p in history.points],
            "now": {"at": history.now_at, "price": str(history.now_price)},
            "snapshots": [
                {
                    "id": item.snapshot_id,
                    "taken_at": item.taken_at.isoformat(),
                    "price": str(item.price),
                    "origin": item.origin,
                }
                for item in frozen
            ],
            "is_synthetic": True,
        }

    @app.get("/api/v1/bom/{version}/root")
    def read_root(
        version: str,
        calculation_id: str | None = Query(None),
        calculation_snapshot_id: str | None = Query(None, description=_FROZEN),
    ):
        bom = repository.load(version)
        return _render(
            repositories, bom, (root_node(bom),), calculation_id,
            calculation_snapshot_id,
        )[0]

    @app.get("/api/v1/bom/{version}/children")
    def read_children(
        version: str,
        path: str = Query(..., description="Le nœud à déplier, chemin complet"),
        calculation_id: str | None = Query(
            None, description="Enrichit chaque ligne des chiffres de ce calcul"
        ),
        calculation_snapshot_id: str | None = Query(None, description=_FROZEN),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        # Aucun paramètre de profondeur : le dépliage se fait nœud par nœud, et
        # le navigateur ne doit jamais pouvoir demander le graphe entier.
        bom = repository.load(version)
        page = children_of_path(bom, path, limit=limit, offset=offset)
        return {
            "path": path,
            "items": _render(
                repositories, bom, page.items, calculation_id,
                calculation_snapshot_id,
            ),
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
    def read_part(version: str, part_ref: str, calculation_id: str | None = Query(None)):
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
            "material_ref": part.material_ref,
            "material_quantity_kg": (
                _text(dict(bom.children_of(part_ref)).get(part.material_ref)) if part.material_ref else None
            ),
            "mass_kg": _text(part.mass_kg),
            "composition": [
                {
                    "part_ref": child,
                    "label": bom.parts[child].label,
                    "quantity": str(quantity),
                    "unit": bom.parts[child].unit,
                }
                for child, quantity in bom.children_of(part_ref)
            ],
        }
        if calculation_id is not None:
            calculation = repositories.calculations.get(calculation_id)
            line = calculation.lines_by_ref.get(part_ref)
            currency = calculation.display_currency
            payload.update(
                {
                    "cumulative_quantity": _text(line and line.cumulative_quantity),
                    "unit_cost": _money(line and line.full_unit_cost, currency),
                    "own_unit_cost": _money(line and line.own_unit_cost, currency),
                    "own_contribution": _money(line and line.own_contribution, currency),
                    "price_status": calculation.price_status_of(part_ref).value,
                }
            )
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
        max_paths: int = Query(50, ge=1, le=200),
    ):
        bom = repository.load(version)
        hits = search_parts(bom, q, limit=limit, max_paths=max_paths)
        summary = search_summary(bom, q)
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
            ],
            "total_parts": summary.total_parts,
            "total_occurrences": summary.total_occurrences,
        }


def _render(
    repositories, bom, nodes, calculation_id: str | None,
    calculation_snapshot_id: str | None = None,
) -> list[dict]:
    """Les lignes, avec ou sans les chiffres d'un calcul.

    Sans `calculation_id` ni snapshot, aucun champ monétaire n'est renvoyé —
    pas même à zéro : un zéro se lit comme un prix.

    Un snapshot de calcul ouvert apporte son calcul figé **et** sa copie des
    réglages : les marques ●/○ disent ce que le gel contenait, pas ce que le
    scénario vivant est devenu depuis (ADR-0014).
    """
    if calculation_snapshot_id is not None:
        snapshot = repositories.calculation_snapshots.get(calculation_snapshot_id)
        if calculation_id is not None and calculation_id != snapshot.calculation_id:
            raise CalculationSnapshotMismatch(
                f"le snapshot {snapshot.id} fige le calcul {snapshot.calculation_id},"
                f" pas {calculation_id}"
            )
        calculation = repositories.calculations.get(snapshot.calculation_id)
        scenario = frozen_scenario(snapshot)
    elif calculation_id is None:
        return [_node_payload(node) for node in nodes]
    else:
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
            # Poids de cette occurrence dans le total. Ne se somme pas entre
            # niveaux ; absent si la ligne n'a pas de prix.
            **(
                {"share_of_total_pct": str(costed.share_of_total_pct)}
                if costed.share_of_total_pct is not None
                else {}
            ),
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


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _decimal(value: Decimal) -> str:
    return str(value.quantize(SCALE))


def _plant_payload(plant) -> dict:
    return {
        "plant_id": plant.plant_id,
        "label": plant.label,
        "origin_country": plant.origin_country,
        "price_coefficient": str(plant.price_coefficient),
        "lead_time_days": plant.lead_time_days,
        "transport_co2_kg_per_kg": str(plant.transport_co2_kg_per_kg),
        "is_default": plant.is_default,
    }


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
        "after_sales_quantity": _decimal(node.after_sales_quantity),
        "has_children": node.has_children,
        "child_count": node.child_count,
        "parent_count": node.parent_count,
        "occurrence_count": node.occurrence_count,
    }
