/**
 * Ce que l'API renvoie.
 *
 * Un montant est une **chaîne**, jamais un nombre. Ce n'est pas une précaution
 * de sérialisation : c'est ce qui rend l'arithmétique impossible ici par
 * construction. `a.amount + b.amount` concatène deux chaînes et saute aux yeux
 * en relecture, là où `a + b` aurait produit un total faux et plausible.
 *
 * Le front affiche ce que l'API renvoie ; il ne recalcule rien (ADR-0009).
 */

export type Money = {
  /** Décimal exact, à l'échelle des données. Se formate, ne s'additionne pas. */
  readonly amount: string;
  readonly currency: string;
};

export type ValuationMode = "purchased" | "manufactured";

export type TreeLine = {
  readonly path: string;
  readonly part_ref: string;
  readonly label: string;
  readonly system: string;
  readonly valuation_mode: ValuationMode;
  readonly unit: string;
  readonly edge_quantity: string;
  readonly has_children: boolean;
  readonly child_count: number;
  /** Nombre de parents directs. */
  readonly parent_count: number;
  /** Nombre de chemins depuis la racine : le « utilisée à N endroits ». */
  readonly occurrence_count: number;

  // Présents uniquement quand un calcul est demandé.
  readonly quantity_on_path?: string;
  readonly unit_cost?: Money | null;
  readonly own_unit_cost?: Money | null;
  /** Ce que pèse cette occurrence, enfants compris. Ne se somme pas. */
  readonly rolled_up_contribution?: Money | null;
  /** La contribution propre : celle qui se somme au total. */
  readonly own_contribution?: Money | null;
  readonly price_status?: "OK" | "MISSING" | "FALLBACK";
  readonly is_modified?: boolean;
  readonly has_modified_descendant?: boolean;
};

export type Page<T> = {
  readonly items: readonly T[];
  readonly total: number;
  readonly limit: number;
  readonly offset: number;
};

export type Occurrence = {
  readonly path: string;
  readonly path_labels: readonly string[];
  readonly quantity_on_path: string;
};

export type SearchHit = {
  readonly part_ref: string;
  readonly label: string;
  readonly system: string;
  readonly occurrence_count: number;
  readonly paths: readonly string[];
  readonly paths_truncated: boolean;
};

export type CalculationState =
  | "NEVER_RUN"
  | "UP_TO_DATE"
  | "PARAMETERS_CHANGED"
  | "NO_PRICES";

export type Scenario = {
  readonly id: string;
  readonly bom_version: string;
  readonly display_currency: string;
  readonly labour_rate: string;
  readonly active_rules: readonly string[];
  readonly parameters: readonly ScenarioParameter[];
  readonly calculation_state: CalculationState;
  readonly stale_reason: string | null;
};

export type ScenarioParameter = {
  readonly part_ref: string;
  readonly scope: "part" | "path";
  readonly path: string | null;
  readonly supplier_id: string | null;
  readonly plant_id: string | null;
  readonly price_override: string | null;
  readonly price_override_justification: string | null;
};

export type ParameterAck = {
  readonly parameter_id: string;
  readonly scope: string;
  readonly part_ref: string;
  readonly affects_occurrences: number;
  /** La phrase que l'écran affiche telle quelle : la portée n'est pas déduite ici. */
  readonly scope_label: string;
  readonly calculation_state: CalculationState;
  readonly stale_reason: string | null;
};

export type SystemTotal = {
  readonly system: string;
  readonly cost: Money;
  readonly cost_share_pct: string;
};

export type Contributor = {
  readonly part_ref: string;
  readonly label: string;
  readonly system: string;
  readonly cumulative_quantity: string;
  readonly own_contribution: Money;
  readonly share_pct: string;
  readonly first_path: string;
};

export type Calculation = {
  readonly id: string;
  readonly scenario_id: string;
  readonly status: "OK" | "DEGRADED" | "INCOMPLETE" | "FAILED";
  readonly bom_version: string;
  readonly computed_at: string;
  readonly input_digest: string;
  readonly display_currency: string;
  readonly total_cost: Money;
  readonly price_snapshot: {
    readonly id: string;
    readonly age_seconds: number;
    readonly status: "FRESH" | "STALE" | "DEGRADED";
  };
  readonly systems: readonly SystemTotal[];
  readonly top_cost_contributors: readonly Contributor[];
  readonly parts_without_price: readonly string[];
};

export type Supplier = {
  readonly supplier_id: string;
  readonly name: string;
  readonly price_multiplier: string;
  readonly plants: readonly {
    readonly plant_id: string;
    readonly label: string;
    readonly origin_country: string;
    readonly price_coefficient: string;
    readonly lead_time_days: number;
    readonly is_default: boolean;
  }[];
};

export type ApiError = {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly details: Record<string, unknown>;
  };
};
