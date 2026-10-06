"""Scénarios et calculs.

Ces routes ne décident de rien : elles lisent, appellent un cas d'usage, et
sérialisent. Le total, la décomposition, la portée d'un paramètre et l'état
d'obsolescence viennent tous de la couche application — le navigateur ne
recalcule jamais (ADR-0009).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import FastAPI, Path, Query, Request
from pydantic import BaseModel, Field

from ...application import manage_scenarios
from ...application.compare_scenarios import (
    IncomparableCalculations,
    compare_calculations,
)
from ...application.recommend_sourcing import (
    IncompleteBaseline,
    SourcingConstraints,
    apply_recommendations,
    recommend,
)
from ...application.browse_bom import where_used
from ...application.calculation_issues import calculation_issues
from ...application.calculation_state import scope_label, state_of
from ...application.explain_calculation import (
    AssemblyBreakdown,
    CatalogueBreakdown,
    LineExplanation,
    OverrideBreakdown,
    explain_line,
)
from ...application.price_resolution import (
    NoSupplierForPart,
    ParameterNotApplicable,
    PlantNotAvailableForSupplier,
    PriceOverrideNeedsJustification,
    resolve_unit_prices,
)
from ...application.run_calculation import (
    input_digest,
    run_calculation,
    with_contributors,
)
from ...application.scenario import Scenario, ScenarioParameter, Scope
from ...application.take_snapshot import TookFallback, snapshot_for_bom
from .errors import error_response
from .price_source import previous_for, price_source

SCALE = Decimal("0.000001")


class NoPriceSnapshot(Exception):
    """Aucun snapshot, même périmé : rien ne peut être calculé."""


class NewParameter(BaseModel):
    scope: Scope = Field(
        default="part",
        description="`part` cible toutes les occurrences de la pièce ; `path` une seule occurrence.",
    )
    path: str | None = Field(
        default=None,
        description="Chemin complet depuis la racine, obligatoire uniquement avec `scope = path`.",
        examples=["VEH-MULTIPLA-16V/GMP-ASSY/ENG-BLOCK-ASSY/FIX-M6-16"],
    )
    supplier_id: str | None = Field(
        default=None, description="Fournisseur choisi pour une pièce achetée.",
        examples=["SUP-BULLONI"],
    )
    plant_id: str | None = Field(
        default=None, description="Usine du fournisseur choisi, donc provenance de la pièce.",
        examples=["PLT-BULLONI-TR"],
    )
    price_override: Decimal | None = Field(
        default=None, description="Prix unitaire forcé ; exige une justification non vide.",
    )
    price_override_justification: str | None = Field(
        default=None, description="Motif obligatoire lorsqu'un prix unitaire est forcé.",
    )
    labour_minutes: Decimal | None = Field(
        default=None, description="Temps de main-d'œuvre, applicable uniquement à un ensemble fabriqué.",
    )
    labour_rate: Decimal | None = Field(
        default=None,
        description=(
            "Taux horaire propre à cette cible, à la place de celui du scénario ; "
            "applicable uniquement à un ensemble fabriqué."
        ),
        examples=["75.00"],
    )
    purchase_currency: str | None = Field(
        default=None, description="Devise d'achat de la pièce, distincte de la devise d'affichage.",
        examples=["EUR"],
    )


class StoredParameter(NewParameter):
    part_ref: str = Field(
        description="Référence de la pièce ciblée dans la nomenclature.",
        examples=["FIX-M6-16"],
    )


class NewScenario(BaseModel):
    bom_version: str = Field(
        description="Version de nomenclature utilisée par le scénario.",
        examples=["bom-multipla-2026-09-22"],
    )
    name: str = Field(
        description="Nom humain permettant de retrouver le scénario dans la liste.",
        examples=["RECETTE - Base"],
    )
    display_currency: str = Field(
        default="EUR", description="Devise d'affichage des résultats.",
    )
    labour_rate: Decimal = Field(
        description="Coût d'une heure de main-d'œuvre.", examples=["42.000000"],
    )
    active_rules: list[str] = Field(
        default_factory=lambda: ["labour"],
        description="Règles actives. Une liste vide désactive notamment la main-d'œuvre.",
    )
    parameters: list[StoredParameter] = Field(
        default_factory=list, description="Paramètres initiaux, éventuellement vides.",
    )
    include_after_sales: bool = Field(
        default=False,
        description="Compter les pièces de rechange livrées avec le véhicule (SAV).",
    )


class ScenarioSettings(BaseModel):
    include_after_sales: bool | None = Field(
        default=None,
        description=(
            "Compter les pièces de rechange livrées avec le véhicule (SAV) en plus "
            "des pièces montées. Basculer rend le dernier calcul obsolète."
        ),
    )
    labour_rate: Decimal | None = Field(
        default=None,
        description="Coût d'une heure de main-d'œuvre. Le dernier calcul devient obsolète.",
        examples=["42.000000"],
    )


class LiveCalculation(BaseModel):
    scenario_id: str = Field(
        description="Identifiant `scn-…` du scénario à calculer aux prix actuels de l'API.",
    )


class DuplicateScenario(BaseModel):
    name: str = Field(
        description="Nom de la copie. La copie recevra automatiquement un nouvel identifiant.",
        examples=["RECETTE - Variante Turquie"],
    )


class NewCalculation(BaseModel):
    scenario_id: str = Field(
        description="Identifiant `scn-…` du scénario à calculer, obtenu à la création ou dans la liste.",
        examples=["scn-123456789abc"],
    )
    price_snapshot_id: str | None = Field(
        default=None,
        description="Identifiant `snp-…` retourné par la liste des snapshots. `null` utilise le plus récent.",
        examples=["snp-2026-10-06-1923-7a9947"],
    )


class CompareScenarios(BaseModel):
    scenario_a_id: str = Field(
        description="Identifiant du scénario de référence A, par exemple l'id renvoyé par `POST /scenarios`.",
        examples=["scn-111111111111"],
    )
    scenario_b_id: str = Field(
        description="Identifiant de la variante B, par exemple l'id renvoyé par `POST /scenarios/{id}/duplicate`.",
        examples=["scn-222222222222"],
    )
    price_snapshot_id: str | None = Field(
        default=None,
        description="Snapshot commun aux deux calculs. `null` sélectionne automatiquement le plus récent.",
        examples=["snp-2026-10-06-1923-7a9947"],
    )


class SourcingQuery(BaseModel):
    forbidden_origins: list[str] = Field(
        default_factory=list,
        description="Codes pays ISO à deux lettres interdits, par exemple `RU`.",
    )
    max_lead_time_days: int | None = Field(
        default=None, ge=0,
        description="Délai fournisseur maximal. `null` n'impose aucune limite.",
    )
    price_snapshot_id: str | None = Field(
        default=None,
        description="Snapshot utilisé pour évaluer les options. `null` utilise le plus récent.",
        examples=["snp-2026-10-06-1923-7a9947"],
    )


class RecommendSourcing(SourcingQuery):
    name: str = Field(
        description="Nom du nouveau scénario optimisé qui sera créé.",
        examples=["RECETTE - Optimisé"],
    )
    accepted_part_refs: list[str] | None = Field(
        default=None,
        description="`null` applique tout, `[]` rien, une liste applique seulement ces pièces.",
        examples=[["FIX-M6-16"]],
    )


def register_calculation_routes(app: FastAPI, repositories) -> None:
    @app.exception_handler(manage_scenarios.InvalidScenario)
    async def _invalid_scenario(_: Request, error: manage_scenarios.InvalidScenario):
        return error_response(422, "INVALID_SCENARIO", str(error))

    @app.exception_handler(NoSupplierForPart)
    async def _no_supplier(_: Request, error: NoSupplierForPart):
        return error_response(422, "NO_SUPPLIER_FOR_PART", str(error))

    @app.exception_handler(ParameterNotApplicable)
    async def _not_applicable(_: Request, error: ParameterNotApplicable):
        return error_response(422, "PARAMETER_NOT_APPLICABLE", str(error))

    @app.exception_handler(PlantNotAvailableForSupplier)
    async def _wrong_plant(_: Request, error: PlantNotAvailableForSupplier):
        return error_response(422, "PLANT_NOT_AVAILABLE_FOR_SUPPLIER", str(error))

    @app.exception_handler(PriceOverrideNeedsJustification)
    async def _needs_justification(_: Request, error: PriceOverrideNeedsJustification):
        return error_response(
            422, "PRICE_OVERRIDE_JUSTIFICATION_REQUIRED", str(error)
        )

    @app.exception_handler(NoPriceSnapshot)
    async def _no_snapshot(_: Request, error: NoPriceSnapshot):
        return error_response(409, "NO_PRICE_SNAPSHOT", str(error))

    @app.exception_handler(IncomparableCalculations)
    async def _incomparable(_: Request, error: IncomparableCalculations):
        return error_response(422, "INCOMPARABLE_SCENARIOS", str(error))

    @app.exception_handler(IncompleteBaseline)
    async def _incomplete_baseline(_: Request, error: IncompleteBaseline):
        return error_response(409, "INCOMPLETE_CALCULATION", str(error))

    @app.post(
        "/api/v1/scenarios", status_code=201, tags=["Scénarios"],
        summary="Créer un scénario",
        description=(
            "Crée un scénario nommé et renvoie son identifiant `scn-…`. "
            "Cet identifiant sert ensuite à le lire, le dupliquer ou le calculer."
        ),
    )
    def create_scenario(payload: NewScenario):
        scenario = Scenario(
            id=f"scn-{uuid.uuid4().hex[:12]}",
            bom_version=payload.bom_version,
            display_currency=payload.display_currency,
            labour_rate=payload.labour_rate,
            active_rules=frozenset(payload.active_rules),
            name=payload.name,
            parameters=tuple(
                ScenarioParameter(**p.model_dump()) for p in payload.parameters
            ),
            include_after_sales=payload.include_after_sales,
        )
        scenario = manage_scenarios.create_scenario(
            scenario, repositories.bom, repositories.scenarios, repositories.sourcing,
        )
        return _scenario_payload(repositories, scenario)

    @app.patch(
        "/api/v1/scenarios/{scenario_id}", tags=["Scénarios"],
        summary="Régler le SAV ou le taux horaire d'un scénario",
        description=(
            "Active ou désactive le comptage des pièces de rechange (SAV), ou "
            "change le taux horaire. Le dernier calcul devient obsolète : "
            "l'empreinte des entrées change."
        ),
    )
    def update_settings(
        scenario_id: Annotated[str, Path(description="Identifiant `scn-…`.")],
        payload: ScenarioSettings,
    ):
        if payload.labour_rate is not None:
            manage_scenarios.set_labour_rate(
                scenario_id, payload.labour_rate, repositories.scenarios,
            )
        if payload.include_after_sales is not None:
            repositories.scenarios.set_after_sales(
                scenario_id, payload.include_after_sales,
            )
        return _scenario_payload(repositories, repositories.scenarios.get(scenario_id))

    @app.get(
        "/api/v1/scenarios", tags=["Scénarios"],
        summary="Lister les scénarios",
        description=(
            "Retourne tous les scénarios du plus récent au plus ancien. "
            "Utilisez cette route pour retrouver les identifiants `scn-…` sans les mémoriser."
        ),
    )
    def list_scenarios():
        scenarios = repositories.scenarios.list_all()
        return {
            "items": [
                _scenario_payload(repositories, scenario)
                for scenario in scenarios
            ],
            "total": len(scenarios),
        }

    @app.post(
        "/api/v1/scenarios/{scenario_id}/duplicate", status_code=201,
        tags=["Scénarios"], summary="Dupliquer un scénario",
        description=(
            "Copie le scénario source et renvoie un nouvel identifiant `scn-…`. "
            "Ce nouvel identifiant est celui de la variante à utiliser comme `scenario_b_id` "
            "dans une comparaison."
        ),
    )
    def duplicate_scenario(
        scenario_id: Annotated[
            str,
            Path(
                description="Identifiant `scn-…` du scénario source à copier.",
                examples=["scn-111111111111"],
            ),
        ],
        payload: DuplicateScenario,
    ):
        copied = manage_scenarios.duplicate_scenario(
            scenario_id, name=payload.name, scenario_id=f"scn-{uuid.uuid4().hex[:12]}",
            boms=repositories.bom, scenarios=repositories.scenarios,
            sourcing=repositories.sourcing,
        )
        return _scenario_payload(repositories, copied)

    @app.get(
        "/api/v1/scenarios/{scenario_id}", tags=["Scénarios"],
        summary="Lire un scénario",
        description="Relit un scénario, ses paramètres et l'état de son calcul.",
    )
    def read_scenario(
        scenario_id: Annotated[
            str,
            Path(
                description="Identifiant `scn-…` obtenu à la création, à la duplication ou dans la liste.",
                examples=["scn-111111111111"],
            ),
        ],
    ):
        return _scenario_payload(
            repositories, repositories.scenarios.get(scenario_id)
        )

    @app.delete(
        "/api/v1/scenarios/{scenario_id}", status_code=204,
        tags=["Scénarios"], summary="Supprimer un scénario",
        description=(
            "Supprime définitivement le scénario. Ses paramètres et ses calculs "
            "sont supprimés en cascade ; la nomenclature et les snapshots sont conservés."
        ),
    )
    def delete_scenario(
        scenario_id: Annotated[
            str,
            Path(
                description="Identifiant `scn-…` du scénario à supprimer.",
                examples=["scn-111111111111"],
            ),
        ],
    ):
        if repositories.calculation_snapshots is None:
            # Câblage sans snapshots de calcul : rien ne peut retenir le scénario.
            repositories.scenarios.delete(scenario_id)
            return
        manage_scenarios.delete_scenario(
            scenario_id,
            scenarios=repositories.scenarios,
            snapshots_repo=repositories.calculation_snapshots,
        )

    @app.put(
        "/api/v1/scenarios/{scenario_id}/parameters/{target:path}",
        tags=["Scénarios"], summary="Ajouter ou remplacer un paramètre",
        description=(
            "`target` est une référence de pièce avec `scope = part`, par exemple `FIX-M6-16`, "
            "ou un chemin complet avec `scope = path`. La réponse renvoie le `parameter_id` "
            "nécessaire uniquement pour supprimer ensuite ce paramètre."
        ),
    )
    def put_parameter(
        scenario_id: Annotated[
            str,
            Path(description="Identifiant `scn-…` du scénario à modifier."),
        ],
        target: Annotated[
            str,
            Path(
                description=(
                    "Référence de pièce (`FIX-M6-16`) ou chemin complet de l'occurrence ciblée."
                ),
                examples=["FIX-M6-16"],
            ),
        ],
        payload: NewParameter,
    ):
        scenario = repositories.scenarios.get(scenario_id)
        bom = repositories.bom.load(scenario.bom_version)

        if payload.path is not None and (
            payload.scope != "path" or payload.path != target
        ):
            raise manage_scenarios.InvalidScenario(
                "le chemin doit correspondre à la cible de portée chemin"
            )
        part_ref = target.split("/")[-1] if payload.scope == "path" else target
        parameter = ScenarioParameter(
            part_ref=part_ref,
            scope=payload.scope,
            path=target if payload.scope == "path" else None,
            supplier_id=payload.supplier_id,
            plant_id=payload.plant_id,
            price_override=payload.price_override,
            price_override_justification=payload.price_override_justification,
            labour_minutes=payload.labour_minutes,
            labour_rate=payload.labour_rate,
            purchase_currency=payload.purchase_currency,
        )

        # On valide avant d'écrire : un paramètre refusé ne doit pas laisser de
        # trace, sinon l'écran afficherait un réglage qui n'a jamais pris.
        parameter_id = manage_scenarios.put_parameter(
            scenario_id, parameter, repositories.bom,
            repositories.scenarios, repositories.sourcing,
        )
        occurrences = (
            1 if parameter.scope == "path" else where_used(bom, part_ref, limit=1).total
        )
        state, reason = _state(repositories, repositories.scenarios.get(scenario_id))

        return {
            "parameter_id": parameter_id,
            "scope": parameter.scope,
            "part_ref": part_ref,
            "affects_occurrences": occurrences,
            "scope_label": scope_label(parameter.scope, occurrences=occurrences),
            "calculation_state": state.value,
            "stale_reason": reason,
        }

    @app.delete(
        "/api/v1/scenarios/{scenario_id}/parameters/{parameter_id}",
        tags=["Scénarios"], summary="Supprimer un paramètre",
        description=(
            "Supprime le paramètre identifié par le `parameter_id` renvoyé par le `PUT` "
            "ou par la lecture du scénario."
        ),
    )
    def delete_parameter(
        scenario_id: Annotated[
            str, Path(description="Identifiant `scn-…` du scénario à modifier.")
        ],
        parameter_id: Annotated[
            str,
            Path(
                description="Identifiant `prm-…` renvoyé lors de la création du paramètre.",
                examples=["prm-123456789abc"],
            ),
        ],
    ):
        repositories.scenarios.delete_parameter(scenario_id, parameter_id)
        state, reason = _state(repositories, repositories.scenarios.get(scenario_id))
        return {"calculation_state": state.value, "stale_reason": reason}

    @app.post(
        "/api/v1/calculations", status_code=201, tags=["Calculs"],
        summary="Calculer un scénario",
        description=(
            "Calcule le coût du scénario indiqué. `price_snapshot_id = null` utilise automatiquement "
            "le snapshot de prix le plus récent et la réponse indique l'identifiant réellement utilisé."
        ),
    )
    def create_calculation(payload: NewCalculation):
        scenario = repositories.scenarios.get(payload.scenario_id)
        snapshot = _snapshot(
            repositories, payload.price_snapshot_id, scenario.bom_version
        )
        calculation = _execute_calculation(
            repositories, payload.scenario_id, snapshot, scenario
        )
        return _calculation_payload(calculation)

    @app.post(
        "/api/v1/calculations/live", tags=["Calculs"],
        summary="Calculer aux prix actuels de l'API, sans rien enregistrer",
        description=(
            "Interroge l'API de prix, calcule le scénario avec ces prix et renvoie le "
            "résultat marqué `price_mode = LIVE`. Rien n'est enregistré (ADR-0015) : ni "
            "calcul, ni snapshot de prix. Pour garder un chiffre, figer les prix "
            "(`POST /price-snapshots`) puis calculer. API muette : 503."
        ),
    )
    def create_live_calculation(payload: LiveCalculation):
        scenario = repositories.scenarios.get(payload.scenario_id)
        bom = repositories.bom.load(scenario.bom_version)
        now = repositories.clock()
        outcome = snapshot_for_bom(
            price_source(repositories), bom,
            bom_version=scenario.bom_version, currency=scenario.display_currency,
            previous=previous_for(repositories, scenario.bom_version, scenario.display_currency),
            now=now, snapshot_id=f"live-{uuid.uuid4().hex[:12]}",
        )
        if isinstance(outcome, TookFallback):
            # En direct, le dernier snapshot n'est pas « le prix actuel » : on
            # le dit plutôt que de l'afficher sous ce nom.
            raise PriceSourceError(outcome.reason)
        sourcing = repositories.sourcing.load(scenario.bom_version)
        calculation = run_calculation(
            bom=bom,
            scenario=scenario,
            snapshot=outcome.snapshot,
            resolved=resolve_unit_prices(bom, sourcing, outcome.snapshot, scenario),
            now=now,
            calculation_id=f"live-{uuid.uuid4().hex[:12]}",
        )
        repositories.live.keep(calculation)
        return {
            **_calculation_payload(calculation, price_mode="LIVE"),
            "prices_taken_at": now.isoformat(),
        }

    @app.post(
        "/api/v1/scenarios/compare", tags=["Scénarios"],
        summary="Comparer deux scénarios A et B",
        description=(
            "A est le scénario de référence (`scenario_a_id`) et B la variante "
            "(`scenario_b_id`, souvent l'id renvoyé par la duplication). "
            "Le delta retourné vaut B moins A. Un calcul incomplet est refusé : "
            "un prix manquant n'est jamais assimilé à zéro."
        ),
    )
    def compare_scenarios(payload: CompareScenarios):
        scenario_a = repositories.scenarios.get(payload.scenario_a_id)
        scenario_b = repositories.scenarios.get(payload.scenario_b_id)
        if scenario_a.bom_version != scenario_b.bom_version:
            raise IncomparableCalculations(
                "les scénarios doivent utiliser la même version de nomenclature"
            )
        if scenario_a.display_currency != scenario_b.display_currency:
            raise IncomparableCalculations(
                "les scénarios doivent utiliser la même devise d'affichage"
            )
        snapshot = _snapshot(
            repositories, payload.price_snapshot_id, scenario_a.bom_version
        )
        calculation_a = _execute_calculation(
            repositories, payload.scenario_a_id, snapshot
        )
        calculation_b = _execute_calculation(
            repositories, payload.scenario_b_id, snapshot
        )
        return _comparison_payload(
            compare_calculations(calculation_a, calculation_b)
        )

    @app.post(
        "/api/v1/scenarios/{scenario_id}/recommend-sourcing/preview",
        tags=["Scénarios"], summary="Prévisualiser les recommandations de sourcing",
        description=(
            "Évalue les fournisseurs et usines autorisés et explique chaque recommandation, "
            "sans créer de scénario. L'écran s'en sert pour laisser l'utilisateur choisir les "
            "lignes avant `POST /scenarios/{id}/recommend-sourcing`."
        ),
    )
    def preview_sourcing(
        scenario_id: Annotated[
            str,
            Path(description="Identifiant `scn-…` du scénario servant de point de départ."),
        ],
        payload: SourcingQuery,
    ):
        base, snapshot, _, report = _evaluate_sourcing(repositories, scenario_id, payload)
        return {
            "base_scenario_id": base.id,
            "price_snapshot_id": snapshot.id,
            **_report_payload(report, payload, set(), base.display_currency),
        }

    @app.post(
        "/api/v1/scenarios/{scenario_id}/recommend-sourcing", status_code=201,
        tags=["Scénarios"], summary="Créer une variante de sourcing optimisée",
        description=(
            "Évalue les fournisseurs et usines autorisés, explique les recommandations, puis crée "
            "un nouveau scénario indépendant avec un nouvel identifiant `scn-…`. "
            "Le calcul de base doit être complet pour que l'économie annoncée soit fiable."
        ),
    )
    def recommend_sourcing(
        scenario_id: Annotated[
            str,
            Path(description="Identifiant `scn-…` du scénario servant de point de départ."),
        ],
        payload: RecommendSourcing,
    ):
        base, snapshot, baseline, report = _evaluate_sourcing(
            repositories, scenario_id, payload
        )
        recommendations = report.recommendations
        available = {item.part_ref for item in recommendations}
        accepted = (
            available
            if payload.accepted_part_refs is None
            else set(payload.accepted_part_refs)
        )
        unknown = accepted - available
        if unknown:
            raise manage_scenarios.InvalidScenario(
                "aucune recommandation applicable pour : "
                + ", ".join(sorted(unknown))
            )
        optimized = apply_recommendations(
            base,
            recommendations,
            frozenset(accepted),
            scenario_id=f"scn-{uuid.uuid4().hex[:12]}",
            name=payload.name,
        )
        optimized = manage_scenarios.create_scenario(
            optimized,
            repositories.bom,
            repositories.scenarios,
            repositories.sourcing,
        )
        optimized_calculation = _execute_calculation(
            repositories, optimized.id, snapshot
        )
        comparison = compare_calculations(baseline, optimized_calculation)
        return {
            "base_scenario_id": base.id,
            "optimized_scenario": _scenario_payload(repositories, optimized),
            "savings": _money(-comparison.cost_delta, comparison.display_currency),
            **_report_payload(report, payload, accepted, base.display_currency),
        }

    @app.get(
        "/api/v1/calculations/{calculation_id}", tags=["Calculs"],
        summary="Relire un calcul enregistré",
        description=(
            "Retourne exactement le calcul identifié par `calc-…`, avec son total, son snapshot, "
            "son statut et ses principaux contributeurs. L'identifiant est renvoyé par "
            "`POST /api/v1/calculations`."
        ),
    )
    def read_calculation(
        calculation_id: Annotated[
            str,
            Path(
                description="Identifiant `calc-…` renvoyé lors du lancement du calcul.",
                examples=["calc-123456789abc"],
            ),
        ],
    ):
        calculation = repositories.calculations.get(calculation_id)
        if not calculation.top_contributors:
            calculation = with_contributors(
                calculation, repositories.bom.load(calculation.bom_version)
            )
        return _calculation_payload(calculation)

    @app.get(
        "/api/v1/calculations/{calculation_id}/aggregated", tags=["Calculs"],
        summary="Décomposer un calcul par pièce",
        description=(
            "Retourne une ligne agrégée par référence de pièce. La somme de toutes les "
            "`own_contribution` est exactement égale au coût total du calcul."
        ),
    )
    def read_aggregated(
        calculation_id: Annotated[
            str,
            Path(
                description="Identifiant `calc-…` renvoyé par `POST /api/v1/calculations`.",
                examples=["calc-123456789abc"],
            ),
        ],
        limit: int = Query(
            50, ge=1, le=500,
            description="Nombre maximal de pièces renvoyées sur cette page.",
        ),
        offset: int = Query(
            0, ge=0, description="Nombre de pièces à ignorer avant cette page.",
        ),
    ):
        calculation = repositories.calculations.get(calculation_id)
        priced = [line for line in calculation.lines if line.own_contribution is not None]
        window = priced[offset : offset + limit]
        return {
            "items": [_line_payload(line, calculation) for line in window],
            "total": len(priced),
            "limit": limit,
            "offset": offset,
            # Sur l'ensemble des pièces, pas sur la page : c'est la valeur que
            # le test d'invariant compare au total.
            "sum_of_own_contributions": _money(
                sum((line.own_contribution for line in priced), Decimal(0)),
                calculation.display_currency,
            ),
        }

    @app.get("/api/v1/calculations/{calculation_id}/explain")
    def read_explanation(
        calculation_id: str,
        path: str = Query(..., description="La ligne à expliquer, chemin complet"),
    ):
        calculation = repositories.calculations.get(calculation_id)
        explanation = explain_line(
            calculation=calculation,
            bom=repositories.bom.load(calculation.bom_version),
            scenario=repositories.scenarios.get(calculation.scenario_id),
            snapshot=repositories.snapshots.get(calculation.snapshot_id),
            sourcing=repositories.sourcing.load(calculation.bom_version),
            path=path,
        )
        return _explanation_payload(explanation, calculation.display_currency)

    @app.get("/api/v1/calculations/{calculation_id}/issues")
    def read_issues(
        calculation_id: str,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        calculation = repositories.calculations.get(calculation_id)
        issues = calculation_issues(
            calculation, repositories.bom.load(calculation.bom_version)
        )
        return {
            "items": [
                {
                    "kind": issue.kind,
                    "part_ref": issue.part_ref,
                    "label": issue.label,
                    "system": issue.system,
                    "path": issue.path,
                    "cumulative_quantity": _decimal(issue.cumulative_quantity),
                    "occurrence_count": issue.occurrence_count,
                }
                for issue in issues[offset : offset + limit]
            ],
            "total": len(issues),
            "limit": limit,
            "offset": offset,
        }


# ---------------------------------------------------------------- assemblage


def _evaluate_sourcing(repositories, scenario_id: str, query: SourcingQuery):
    invalid_origins = [
        origin
        for origin in query.forbidden_origins
        if len(origin) != 2 or not origin.isalpha()
    ]
    if invalid_origins:
        raise manage_scenarios.InvalidScenario(
            "codes de provenance invalides : " + ", ".join(sorted(invalid_origins))
        )
    base = repositories.scenarios.get(scenario_id)
    bom = repositories.bom.load(base.bom_version)
    sourcing = repositories.sourcing.load(base.bom_version)
    snapshot = _snapshot(repositories, query.price_snapshot_id, base.bom_version)
    baseline = _execute_calculation(repositories, base.id, snapshot)
    report = recommend(
        bom=bom,
        sourcing=sourcing,
        snapshot=snapshot,
        scenario=base,
        baseline=baseline,
        constraints=SourcingConstraints(
            forbidden_origins=frozenset(query.forbidden_origins),
            max_lead_time_days=query.max_lead_time_days,
        ),
    )
    return base, snapshot, baseline, report


def _report_payload(report, query: SourcingQuery, accepted: set, currency: str) -> dict:
    return {
        "constraints": {
            "forbidden_origins": sorted(
                origin.upper() for origin in query.forbidden_origins
            ),
            "max_lead_time_days": query.max_lead_time_days,
        },
        "recommendations": [
            _recommendation_payload(item, item.part_ref in accepted, currency)
            for item in report.recommendations
        ],
        # Une pièce dont le sourcing viole une contrainte sans remède reste
        # telle quelle dans la variante : on le dit plutôt que de le taire.
        "unresolved": [
            {
                "part_ref": item.part_ref,
                "current": {
                    "supplier_id": item.current_supplier_id,
                    "plant_id": item.current_plant_id,
                    "origin_country": item.current_origin,
                },
                "reason": item.reason,
            }
            for item in report.unresolved
        ],
    }


def _snapshot_or_none(repositories, bom_version: str):
    """Le dernier snapshot **de cette nomenclature** : celui d'une autre
    laisserait toutes les pièces sans prix (ADR-0015)."""
    if not repositories.snapshots:
        return None
    return repositories.snapshots.latest(bom_version)


def _snapshot(repositories, snapshot_id: str | None, bom_version: str):
    if snapshot_id is not None:
        return repositories.snapshots.get(snapshot_id)
    snapshot = _snapshot_or_none(repositories, bom_version)
    if snapshot is None:
        raise NoPriceSnapshot(
            "aucun snapshot de prix, même périmé : prenez-en un avant de calculer"
        )
    return snapshot


def _execute_calculation(
    repositories, scenario_id: str, snapshot, scenario: Scenario | None = None,
):
    """Lance et enregistre un calcul ; `scenario` évite de relire un scénario déjà chargé."""
    if scenario is None:
        scenario = repositories.scenarios.get(scenario_id)
    bom = repositories.bom.load(scenario.bom_version)
    sourcing = repositories.sourcing.load(scenario.bom_version)
    resolved = resolve_unit_prices(bom, sourcing, snapshot, scenario)
    calculation = run_calculation(
        bom=bom,
        scenario=scenario,
        snapshot=snapshot,
        resolved=resolved,
        now=repositories.clock(),
        calculation_id=f"calc-{uuid.uuid4().hex[:12]}",
    )
    repositories.calculations.save(calculation)
    return calculation


def _state(repositories, scenario: Scenario, latest=None):
    if latest is None:
        latest = repositories.calculations.latest_for(scenario.id)
    return state_of(
        scenario,
        _snapshot_or_none(repositories, scenario.bom_version),
        last_digest=latest.input_digest if latest else None,
        last_snapshot_id=latest.snapshot_id if latest else None,
    )


def _money(amount: Decimal, currency: str) -> dict:
    """Le montant exact, tel quel.

    L'arrondir ici casserait l'addition : dix montants arrondis ne somment pas
    au total arrondi. L'arrondi est un acte d'affichage, et il a lieu dans le
    navigateur (ADR-0011).
    """
    return {"amount": str(amount), "currency": currency}


def _scenario_payload(repositories, scenario: Scenario) -> dict:
    latest = repositories.calculations.latest_for(scenario.id)
    state, reason = _state(repositories, scenario, latest)
    parameter_ids = repositories.scenarios.parameter_ids(scenario.id)
    return {
        "id": scenario.id,
        "name": scenario.name,
        "bom_version": scenario.bom_version,
        "display_currency": scenario.display_currency,
        "labour_rate": str(scenario.labour_rate),
        "active_rules": sorted(scenario.active_rules),
        # Le snapshot de calcul d'où le scénario est reparti, ou null.
        "derived_from": scenario.derived_from,
        "include_after_sales": scenario.include_after_sales,
        # La nomenclature porte-t-elle du SAV ? Sinon l'interrupteur ne change
        # rien, et l'écran le dit au lieu de le laisser basculer pour rien.
        "after_sales_available": _has_after_sales(repositories, scenario.bom_version),
        "parameters": [
            {
                "parameter_id": parameter_ids[(parameter.part_ref, parameter.path or "")],
                "part_ref": parameter.part_ref,
                "scope": parameter.scope,
                "path": parameter.path,
                "supplier_id": parameter.supplier_id,
                "plant_id": parameter.plant_id,
                "purchase_currency": parameter.purchase_currency,
                "labour_minutes": (
                    str(parameter.labour_minutes)
                    if parameter.labour_minutes is not None
                    else None
                ),
                "labour_rate": (
                    str(parameter.labour_rate)
                    if parameter.labour_rate is not None
                    else None
                ),
                "price_override": (
                    str(parameter.price_override)
                    if parameter.price_override is not None
                    else None
                ),
                "price_override_justification": parameter.price_override_justification,
            }
            for parameter in scenario.parameters
        ],
        "calculation_state": state.value,
        "stale_reason": reason,
        # Relire ce calcul suffit pour réafficher un scénario « à jour » ; en
        # relancer un à chaque ouverture remplirait la table pour rien.
        "last_calculation_id": latest.id if latest else None,
    }


def _has_after_sales(repositories, bom_version: str) -> bool:
    try:
        return repositories.bom.load(bom_version).has_after_sales
    except Exception:  # noqa: BLE001 - une version illisible n'a pas de SAV à offrir
        return False


def _calculation_payload(calculation, price_mode: str = "SNAPSHOT") -> dict:
    currency = calculation.display_currency
    return {
        "id": calculation.id,
        # LIVE : prix lus à l'instant, résultat non enregistré (ADR-0015).
        "price_mode": price_mode,
        "scenario_id": calculation.scenario_id,
        "status": calculation.status.value,
        "bom_version": calculation.bom_version,
        "engine_version": calculation.engine_version,
        "rules_version": calculation.rules_version,
        "active_rules": list(calculation.active_rules),
        "computed_at": calculation.computed_at.isoformat(),
        "input_digest": calculation.input_digest,
        "display_currency": currency,
        "total_cost": _money(calculation.total_cost, currency),
        "total_co2": (
            {"kg_co2e": str(calculation.total_co2)}
            if calculation.total_co2 is not None
            else None
        ),
        "price_snapshot": {
            "id": calculation.snapshot_id,
            "age_seconds": int(calculation.snapshot_age.total_seconds()),
            "status": calculation.snapshot_status,
        },
        "systems": [
            {
                "system": system.system,
                "cost": _money(system.cost, currency),
                "cost_share_pct": str(system.share_pct),
                "co2": {"kg_co2e": str(system.co2)},
                "co2_share_pct": str(system.co2_share_pct),
            }
            for system in calculation.systems
        ],
        "top_cost_contributors": [
            {
                "part_ref": contributor.part_ref,
                "label": contributor.label,
                "system": contributor.system,
                "cumulative_quantity": str(contributor.cumulative_quantity),
                "own_contribution": _money(contributor.own_contribution, currency),
                "share_pct": str(contributor.share_pct),
                "first_path": contributor.first_path,
            }
            for contributor in calculation.top_contributors
        ],
        "top_co2_contributors": [
            {
                "part_ref": contributor.part_ref,
                "label": contributor.label,
                "system": contributor.system,
                "cumulative_quantity": str(contributor.cumulative_quantity),
                "own_co2_contribution": {
                    "kg_co2e": str(contributor.own_co2_contribution)
                },
                "share_pct": str(contributor.share_pct),
                "first_path": contributor.first_path,
            }
            for contributor in calculation.top_co2_contributors
        ],
        "parts_without_price": list(calculation.parts_without_price),
        # Un prix forcé ou une masse absente laisse le coût complet et le CO2
        # incomplet : `total_co2` est alors une somme partielle, et le dire est
        # le seul moyen qu'elle ne soit pas lue comme l'empreinte du véhicule.
        "parts_without_co2": list(calculation.parts_without_co2),
        # Compté ici plutôt que dans le navigateur : chaque ligne relève d'une
        # seule catégorie, et c'est le serveur qui sait laquelle.
        "issue_counts": calculation.issue_counts(),
    }


def _comparison_payload(comparison) -> dict:
    currency = comparison.display_currency
    return {
        "calculation_a_id": comparison.calculation_a_id,
        "calculation_b_id": comparison.calculation_b_id,
        "price_snapshot_id": comparison.snapshot_id,
        "total_a": _money(comparison.total_a, currency),
        "total_b": _money(comparison.total_b, currency),
        "cost_delta": _money(comparison.cost_delta, currency),
        # `None` seulement pour un calcul enregistré avant que le moteur ne
        # porte le CO2 (`total_co2` alors NULL en base).
        "co2_delta_kg": (
            str(comparison.co2_delta)
            if comparison.co2_delta is not None
            else None
        ),
        "top_differences": [
            {
                "part_ref": item.part_ref,
                "contribution_a": _money(item.contribution_a, currency),
                "contribution_b": _money(item.contribution_b, currency),
                "delta": _money(item.delta, currency),
                "cumulative_quantity_a": str(item.cumulative_quantity_a),
                "cumulative_quantity_b": str(item.cumulative_quantity_b),
            }
            for item in comparison.top_differences
        ],
    }


def _recommendation_payload(item, accepted: bool, currency: str) -> dict:
    return {
        "part_ref": item.part_ref,
        "accepted": accepted,
        "required_by_constraint": item.required_by_constraint,
        "current": {
            "supplier_id": item.current_supplier_id,
            "plant_id": item.current_plant_id,
            "origin_country": item.current_origin,
            "unit_price": _money(item.current_unit_price, currency),
        },
        "recommended": {
            "supplier_id": item.recommended_supplier_id,
            "plant_id": item.recommended_plant_id,
            "origin_country": item.recommended_origin,
            "lead_time_days": item.recommended_lead_time_days,
            "unit_price": _money(item.recommended_unit_price, currency),
        },
        "affected_quantity": str(item.affected_quantity),
        "estimated_saving": _money(item.estimated_saving, currency),
        "explanation": (
            f"{item.affected_quantity} unité(s) : {item.current_unit_price} - "
            f"{item.recommended_unit_price} par unité"
        ),
    }


def _line_payload(line, calculation) -> dict:
    currency = calculation.display_currency
    explanation = calculation.explanations.get(line.part_ref)
    payload = {
        "part_ref": line.part_ref,
        "cumulative_quantity": str(line.cumulative_quantity),
        "occurrence_count": line.occurrence_count,
        "own_unit_cost": _money(line.own_unit_cost, currency),
        "own_contribution": _money(line.own_contribution, currency),
        "own_co2_contribution": (
            {"kg_co2e": str(line.own_co2_contribution)}
            if line.own_co2_contribution is not None
            else None
        ),
        "unit_cost": (
            _money(line.full_unit_cost, currency)
            if line.full_unit_cost is not None
            else None
        ),
    }
    if explanation is not None:
        payload["price_source"] = {
            "supplier_id": explanation.supplier_id,
            "plant_id": explanation.plant_id,
            "origin_country": explanation.origin_country,
            "is_overridden": explanation.is_overridden,
        }
    return payload


#: Ce que dit `price_source.reason` pour chaque statut de ligne.
PRICE_REASONS = {
    "OK": None,
    "FALLBACK": "Absent de la réponse de l'API : dernier prix connu retenu",
    "QUARANTINED": (
        "Valeur refusée (journal de quarantaine) : dernier prix sain retenu"
    ),
    "MISSING": "Aucun prix connu, ni frais ni ancien : le total est partiel",
}


def _explanation_payload(explanation: LineExplanation, currency: str) -> dict:
    parameter = explanation.applied_parameter
    status = explanation.price_status
    return {
        "path": explanation.path,
        "part_ref": explanation.part_ref,
        "valuation_mode": explanation.valuation_mode,
        "unit_cost_breakdown": _breakdown_payload(explanation.breakdown, currency),
        "quantity": {
            "on_path": _decimal(explanation.quantity_on_path),
            "cumulative_in_vehicle": _decimal(explanation.cumulative_quantity),
            "unit": explanation.unit,
        },
        "occurrence_count": explanation.occurrence_count,
        "applied_parameter": (
            None
            if parameter is None
            else {
                "scope": parameter.scope,
                "scope_label": scope_label(
                    parameter.scope, occurrences=explanation.occurrence_count
                ),
                "supplier_id": parameter.supplier_id,
                "plant_id": parameter.plant_id,
                "price_override": _optional_money(parameter.price_override, currency),
            }
        ),
        "parameters_changed_since_calculation": explanation.parameters_changed_since,
        "applied_rules": list(explanation.applied_rules),
        "price_source": {
            "snapshot_id": explanation.snapshot_id,
            "status": status,
            # La date d'un prix de repli est celle du snapshot qui l'a repris,
            # pas celle du prix : on ne la donne pas plutôt que de la donner
            # fausse. Remonter la chaîne des replis reste à faire.
            "as_of": (
                explanation.snapshot_taken_at.isoformat()
                if status in ("OK", None)
                else None
            ),
            "reason": PRICE_REASONS.get(status),
        },
    }


def _breakdown_payload(breakdown, currency: str) -> dict | None:
    if breakdown is None:
        return None
    if isinstance(breakdown, CatalogueBreakdown):
        factors = (
            breakdown.reference_price,
            breakdown.supplier_multiplier,
            breakdown.plant_coefficient,
        )
        return {
            "kind": "catalogue",
            "reference_price": _money(breakdown.reference_price, currency),
            "supplier": {
                "supplier_id": breakdown.supplier_id,
                "name": breakdown.supplier_name,
                "multiplier": _optional_decimal(breakdown.supplier_multiplier),
            },
            "plant": {
                "plant_id": breakdown.plant_id,
                "origin": breakdown.origin_country,
                "coefficient": _optional_decimal(breakdown.plant_coefficient),
            },
            "formula": (
                " × ".join(_decimal(factor) for factor in factors)
                if None not in factors
                else None
            ),
            "unit_cost": _money(breakdown.unit_cost, currency),
            # Faux si le sourcing a changé depuis le calcul : la formule ne
            # redonne plus le prix enregistré, et l'écran doit le dire.
            "reproduced": breakdown.reproduced,
        }
    if isinstance(breakdown, OverrideBreakdown):
        return {
            "kind": "override",
            "unit_cost": _money(breakdown.unit_cost, currency),
            "justification": breakdown.justification,
        }
    assert isinstance(breakdown, AssemblyBreakdown)
    return {
        "kind": "assembly",
        "children": [
            {
                "part_ref": child.part_ref,
                "quantity": _decimal(child.quantity),
                "unit_cost": _optional_money(child.unit_cost, currency),
                "contribution": _optional_money(child.contribution, currency),
            }
            for child in breakdown.children
        ],
        "children_cost": _optional_money(breakdown.children_cost, currency),
        "labour": {
            "labour_minutes": _optional_decimal(breakdown.labour_minutes),
            "labour_rate": _money(breakdown.labour_rate, currency),
            "amount": _optional_money(breakdown.labour_cost, currency),
        },
        "unit_cost": _optional_money(breakdown.unit_cost, currency),
    }


def _optional_money(amount: Decimal | None, currency: str) -> dict | None:
    return None if amount is None else _money(amount, currency)


def _decimal(value: Decimal) -> str:
    return str(value.quantize(SCALE))


def _optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else _decimal(value)
