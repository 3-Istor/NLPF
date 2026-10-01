/**
 * Le client HTTP.
 *
 * Il transporte, il ne transforme pas : aucune addition, aucune conversion,
 * aucun arrondi. Ce qui arrive de l'API arrive tel quel jusqu'aux composants.
 */

import type {
  Calculation,
  Comparison,
  Occurrence,
  Page,
  ParameterAck,
  QuarantineJournal,
  Scenario,
  SearchResponse,
  SourcingConstraints,
  SourcingPreview,
  SourcingVariant,
  TreeLine,
} from "./types";

export class ApiFailure extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = body?.error;
    throw new ApiFailure(
      error?.code ?? "UNKNOWN",
      error?.message ?? response.statusText,
      response.status,
    );
  }
  // Une suppression répond 204, sans corps à lire.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});

const withCalculation = (calculationId: string | null) =>
  calculationId ? `&calculation_id=${encodeURIComponent(calculationId)}` : "";

export const api = {
  root: (version: string, calculationId: string | null) =>
    call<TreeLine>(
      `/bom/${version}/root?${withCalculation(calculationId).slice(1)}`,
    ),

  /** Les enfants directs d'un nœud. Il n'existe pas de paramètre de profondeur. */
  children: (version: string, path: string, calculationId: string | null) =>
    call<Page<TreeLine> & { path: string }>(
      `/bom/${version}/children?path=${encodeURIComponent(path)}` +
        withCalculation(calculationId),
    ),

  whereUsed: (version: string, partRef: string) =>
    call<Page<Occurrence> & { part_ref: string; occurrence_count: number }>(
      `/bom/${version}/where-used?part_ref=${encodeURIComponent(partRef)}`,
    ),

  /** Au plus `maxPaths` chemins par pièce ; les totaux comptent tout. */
  search: (version: string, query: string, maxPaths = 50) =>
    call<SearchResponse>(
      `/bom/${version}/search?q=${encodeURIComponent(query)}&max_paths=${maxPaths}`,
    ),

  part: (version: string, partRef: string) =>
    call<Record<string, unknown>>(`/bom/${version}/parts/${partRef}`),

  createScenario: (body: {
    bom_version: string;
    name: string;
    display_currency: string;
    labour_rate: string;
  }) =>
    call<Scenario>("/scenarios", { method: "POST", body: JSON.stringify(body) }),

  scenario: (id: string) => call<Scenario>(`/scenarios/${id}`),

  /** Du plus récent au plus ancien. */
  scenarios: () =>
    call<{ items: Scenario[]; total: number }>("/scenarios"),

  duplicateScenario: (id: string, name: string) =>
    call<Scenario>(`/scenarios/${id}/duplicate`, post({ name })),

  deleteScenario: (id: string) =>
    call<void>(`/scenarios/${id}`, { method: "DELETE" }),

  deleteParameter: (scenarioId: string, parameterId: string) =>
    call<{ calculation_state: string; stale_reason: string | null }>(
      `/scenarios/${scenarioId}/parameters/${parameterId}`,
      { method: "DELETE" },
    ),

  /** Recalcule A et B sur un même snapshot ; le delta vaut B − A. */
  compare: (scenarioA: string, scenarioB: string) =>
    call<Comparison>(
      "/scenarios/compare",
      post({ scenario_a_id: scenarioA, scenario_b_id: scenarioB }),
    ),

  /** Les recommandations, sans rien créer. */
  previewSourcing: (scenarioId: string, constraints: SourcingConstraints) =>
    call<SourcingPreview>(
      `/scenarios/${scenarioId}/recommend-sourcing/preview`,
      post(constraints),
    ),

  /** Crée la variante avec les seules lignes acceptées. */
  createSourcingVariant: (
    scenarioId: string,
    body: SourcingConstraints & {
      name: string;
      accepted_part_refs: readonly string[];
      price_snapshot_id: string;
    },
  ) =>
    call<SourcingVariant>(
      `/scenarios/${scenarioId}/recommend-sourcing`,
      post(body),
    ),

  putParameter: (
    scenarioId: string,
    target: string,
    body: Record<string, unknown>,
  ) =>
    call<ParameterAck>(
      `/scenarios/${scenarioId}/parameters/${encodeURIComponent(target)}`,
      { method: "PUT", body: JSON.stringify(body) },
    ),

  calculate: (scenarioId: string) =>
    call<Calculation>("/calculations", {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId }),
    }),

  calculation: (id: string) => call<Calculation>(`/calculations/${id}`),

  /** Les valeurs refusées à la prise de ce snapshot ; vide s'il est sain. */
  quarantine: (snapshotId: string) =>
    call<QuarantineJournal>(
      `/price-snapshots/${encodeURIComponent(snapshotId)}/quarantine`,
    ),
};
