/**
 * Le client HTTP.
 *
 * Il transporte, il ne transforme pas : aucune addition, aucune conversion,
 * aucun arrondi. Ce qui arrive de l'API arrive tel quel jusqu'aux composants.
 */

import type {
  BomVersion,
  Calculation,
  PriceHistoryResponse,
  PriceSnapshotSummary,
  SupplierParts,
  SupplierSummary,
  CalculationSnapshot,
  CalculationSnapshotSummary,
  Comparison,
  Occurrence,
  Page,
  ParameterAck,
  QuarantineJournal,
  SnapshotComparison,
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

const withCalculation = (calculationId: string | null, snapshotId?: string | null) =>
  (calculationId ? `&calculation_id=${encodeURIComponent(calculationId)}` : "") +
  (snapshotId ? `&calculation_snapshot_id=${encodeURIComponent(snapshotId)}` : "");

export const api = {
  suppliers: (version: string) =>
    call<{ items: SupplierSummary[] }>(`/bom/${version}/suppliers`),

  supplierParts: (version: string, supplierId: string) =>
    call<SupplierParts>(
      `/bom/${version}/suppliers/${encodeURIComponent(supplierId)}/parts`,
    ),

  /** L'année simulée d'une pièce achetée, et ses prix figés. */
  priceHistory: (version: string, partRef: string, currency = "EUR") =>
    call<PriceHistoryResponse>(
      `/bom/${version}/parts/${encodeURIComponent(partRef)}/price-history` +
        `?currency=${encodeURIComponent(currency)}`,
    ),

  /** Les nomenclatures chargées, la plus récente d'abord. */
  bomVersions: () => call<{ items: BomVersion[] }>("/bom/versions"),

  /**
   * `snapshotId` : le snapshot de calcul ouvert. Le serveur marque alors les
   * lignes d'après sa copie des réglages, pas d'après le scénario vivant.
   */
  root: (version: string, calculationId: string | null, snapshotId?: string | null) =>
    call<TreeLine>(
      `/bom/${version}/root?${withCalculation(calculationId, snapshotId).slice(1)}`,
    ),

  /** Les enfants directs d'un nœud. Il n'existe pas de paramètre de profondeur. */
  children: (
    version: string,
    path: string,
    calculationId: string | null,
    snapshotId?: string | null,
  ) =>
    call<Page<TreeLine> & { path: string }>(
      `/bom/${version}/children?path=${encodeURIComponent(path)}` +
        withCalculation(calculationId, snapshotId),
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

  /** Compter ou non le SAV. Le dernier calcul devient obsolète. */
  setAfterSales: (id: string, include: boolean) =>
    call<Scenario>(`/scenarios/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ include_after_sales: include }),
    }),

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

  /** Aux prix actuels de l'API ; rien n'est enregistré. */
  calculateLive: (scenarioId: string) =>
    call<Calculation>("/calculations/live", post({ scenario_id: scenarioId })),

  /** Fige les prix actuels de l'API pour cette nomenclature. */
  takePriceSnapshot: (version: string, currency = "EUR") =>
    call<PriceSnapshotSummary>(
      "/price-snapshots",
      post({ bom_version: version, currency }),
    ),

  priceSnapshots: (version: string) =>
    call<{ items: PriceSnapshotSummary[]; total: number }>(
      `/price-snapshots?bom_version=${encodeURIComponent(version)}`,
    ),

  /** Lance un calcul sur le scénario et le fige sous ce nom. */
  freezeCalculation: (scenarioId: string, name: string) =>
    call<CalculationSnapshot>(
      "/calculation-snapshots",
      post({ scenario_id: scenarioId, name }),
    ),

  /** Du plus récent au plus ancien. */
  calculationSnapshots: (version: string) =>
    call<{ items: CalculationSnapshotSummary[]; total: number }>(
      `/calculation-snapshots?bom_version=${encodeURIComponent(version)}`,
    ),

  /** Compare deux calculs figés : aucun recalcul, rien d'enregistré. */
  compareCalculationSnapshots: (snapshotA: string, snapshotB: string) =>
    call<SnapshotComparison>(
      "/calculation-snapshots/compare",
      post({ snapshot_a_id: snapshotA, snapshot_b_id: snapshotB }),
    ),

  calculationSnapshot: (id: string) =>
    call<CalculationSnapshot>(
      `/calculation-snapshots/${encodeURIComponent(id)}`,
    ),

  /**
   * « Repartir de ce snapshot » : un scénario neuf avec exactement sa copie.
   * Refus `SNAPSHOT_SETTINGS_NOT_APPLICABLE` : le message nomme les pièces.
   */
  deriveScenario: (snapshotId: string, name: string) =>
    call<Scenario>(
      `/calculation-snapshots/${encodeURIComponent(snapshotId)}/derive`,
      post({ name }),
    ),

  /** Les valeurs refusées à la prise de ce snapshot ; vide s'il est sain. */
  quarantine: (snapshotId: string) =>
    call<QuarantineJournal>(
      `/price-snapshots/${encodeURIComponent(snapshotId)}/quarantine`,
    ),
};
