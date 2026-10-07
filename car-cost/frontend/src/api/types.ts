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

/** Une masse de CO₂ équivalent, en kg. Comme `Money` : une chaîne, jamais sommée ici. */
export type Co2 = {
  readonly kg_co2e: string;
};

export type ValuationMode = "purchased" | "manufactured";

/**
 * D'où vient le prix d'une ligne. Décidé par le serveur, affiché tel quel.
 *
 * - `FALLBACK` : absent de la réponse de l'API, dernier prix connu retenu ;
 * - `QUARANTINED` : reçu mais refusé, dernier prix sain retenu ;
 * - `MISSING` : aucun prix — jamais un zéro.
 */
export type PriceStatus = "OK" | "FALLBACK" | "QUARANTINED" | "MISSING";

export type TreeLine = {
  readonly path: string;
  readonly part_ref: string;
  readonly label: string;
  readonly system: string;
  readonly valuation_mode: ValuationMode;
  readonly unit: string;
  readonly edge_quantity: string;
  /** Pièces de rechange portées par l'arête, en plus de la quantité montée. */
  readonly after_sales_quantity?: string;
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
  /** Part du total, déjà calculée par l'API (chaîne décimale) ; absente sans prix. */
  readonly share_of_total_pct?: string | null;
  readonly price_status?: PriceStatus;
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

/** Les totaux comptent tout ce qui correspond, au-delà des chemins servis. */
export type SearchResponse = {
  readonly items: readonly SearchHit[];
  readonly total_parts: number;
  readonly total_occurrences: number;
};

export type CalculationState =
  | "NEVER_RUN"
  | "UP_TO_DATE"
  | "PARAMETERS_CHANGED"
  | "NO_PRICES";

export type Scenario = {
  readonly id: string;
  readonly name: string;
  readonly bom_version: string;
  readonly display_currency: string;
  readonly labour_rate: string;
  readonly active_rules: readonly string[];
  readonly parameters: readonly ScenarioParameter[];
  readonly calculation_state: CalculationState;
  readonly stale_reason: string | null;
  /** Le dernier calcul enregistré, à relire plutôt qu'à relancer. */
  readonly last_calculation_id: string | null;
  /** Le snapshot de calcul dont le scénario est reparti, s'il y en a un. */
  readonly derived_from?: string | null;
  /** Les pièces de rechange (SAV) sont-elles comptées ? */
  readonly include_after_sales?: boolean;
  /** La nomenclature porte-t-elle du SAV ? Sinon l'interrupteur ne change rien. */
  readonly after_sales_available?: boolean;
};

export type ScenarioParameter = {
  readonly parameter_id: string;
  readonly part_ref: string;
  readonly scope: "part" | "path";
  readonly path: string | null;
  readonly supplier_id: string | null;
  readonly plant_id: string | null;
  readonly price_override: string | null;
  readonly price_override_justification: string | null;
  readonly labour_minutes?: string | null;
  /** Taux horaire propre à cette cible ; absent, celui du scénario s'applique. */
  readonly labour_rate?: string | null;
  readonly purchase_currency?: string | null;
};

/** Un calcul figé sous un nom (ADR-0014) ; l'élément d'une liste. */
export type CalculationSnapshotSummary = {
  readonly id: string;
  readonly name: string;
  readonly bom_version: string;
  readonly scenario_id: string;
  readonly scenario_name: string;
  readonly calculation_id: string;
  readonly price_snapshot_id: string;
  readonly created_at: string;
  /** Le snapshot d'où repartait le scénario figé, s'il y en a un. */
  readonly derived_from?: string | null;
};

/** La comparaison de deux calculs figés : les noms viennent du serveur. */
export type SnapshotComparison = Comparison & {
  readonly snapshot_a: { readonly id: string; readonly name: string };
  readonly snapshot_b: { readonly id: string; readonly name: string };
};

export type CalculationSnapshot = CalculationSnapshotSummary & {
  readonly display_currency: string;
  readonly labour_rate: string;
  readonly active_rules: readonly string[];
  readonly parameters: readonly Omit<ScenarioParameter, "parameter_id">[];
  readonly name_history: readonly { name: string; renamed_at: string }[];
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
  readonly co2: Co2;
  readonly co2_share_pct: string;
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

export type Co2Contributor = Omit<Contributor, "own_contribution"> & {
  readonly own_co2_contribution: Co2;
};

export type Calculation = {
  readonly id: string;
  /** LIVE : prix lus à l'instant, résultat jamais enregistré (ADR-0015). */
  readonly price_mode?: "SNAPSHOT" | "LIVE";
  /** En direct : l'heure réelle à laquelle les prix ont été lus. */
  readonly prices_taken_at?: string;
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
  /**
   * `null` : calcul enregistré avant que le moteur ne porte le CO₂. Les
   * chiffres carbone du calcul ne veulent alors rien dire, pas même zéro.
   */
  readonly total_co2: Co2 | null;
  readonly top_co2_contributors: readonly Co2Contributor[];
  readonly parts_without_price: readonly string[];
  /** Non vide : `total_co2` est une somme partielle, pas l'empreinte du véhicule. */
  readonly parts_without_co2: readonly string[];
  /** Une ligne compte dans une seule catégorie. Compté par le serveur. */
  readonly issue_counts: {
    readonly missing_price: number;
    readonly quarantined: number;
    readonly fallback: number;
  };
};

/** Une valeur refusée par le contrôle, telle que le journal la conserve. */
export type QuarantineEntry = {
  readonly part_ref: string;
  readonly currency: string;
  /** Telle que reçue : ce n'était pas forcément un nombre. */
  readonly rejected_value: string;
  readonly reason: string;
  /** `null` : rien n'a pu être retenu, la pièce est sans prix. */
  readonly replacement: Money | null;
  readonly replacement_from_snapshot: string | null;
  readonly detected_at: string;
};

export type QuarantineJournal = {
  readonly snapshot_id: string;
  readonly items: readonly QuarantineEntry[];
};

export type Supplier = {
  readonly supplier_id: string;
  readonly name: string;
  readonly price_multiplier: string;
  /** Le fournisseur retenu par le catalogue quand le scénario n'en choisit pas. */
  readonly is_default?: boolean;
  readonly plants: readonly {
    readonly plant_id: string;
    readonly label: string;
    readonly origin_country: string;
    readonly price_coefficient: string;
    readonly lead_time_days: number;
    readonly is_default: boolean;
  }[];
};

/** B moins A, sur un seul snapshot. Chaque écart est calculé par le serveur. */
export type Comparison = {
  readonly calculation_a_id: string;
  readonly calculation_b_id: string;
  readonly price_snapshot_id: string;
  readonly total_a: Money;
  readonly total_b: Money;
  readonly cost_delta: Money;
  /** `null` tant que le CO₂ n'est pas calculé : ce n'est pas un zéro. */
  readonly co2_delta_kg: string | null;
  readonly top_differences: readonly {
    readonly part_ref: string;
    readonly contribution_a: Money;
    readonly contribution_b: Money;
    readonly delta: Money;
    readonly cumulative_quantity_a: string;
    readonly cumulative_quantity_b: string;
  }[];
};

export type SourcingOption = {
  readonly supplier_id: string;
  readonly plant_id: string;
  readonly origin_country: string;
  readonly unit_price: Money;
};

export type Recommendation = {
  readonly part_ref: string;
  readonly accepted: boolean;
  /** L'option actuelle viole une contrainte : le changement est imposé. */
  readonly required_by_constraint: boolean;
  readonly current: SourcingOption;
  readonly recommended: SourcingOption & { readonly lead_time_days: number };
  readonly affected_quantity: string;
  /** Négative quand une contrainte impose une option plus chère. */
  readonly estimated_saving: Money;
};

export type UnresolvedPart = {
  readonly part_ref: string;
  readonly current: {
    readonly supplier_id: string;
    readonly plant_id: string;
    readonly origin_country: string;
  };
  readonly reason: string;
};

export type SourcingConstraints = {
  readonly forbidden_origins: readonly string[];
  readonly max_lead_time_days: number | null;
};

export type SourcingPreview = {
  readonly base_scenario_id: string;
  readonly price_snapshot_id: string;
  readonly constraints: SourcingConstraints;
  readonly recommendations: readonly Recommendation[];
  readonly unresolved: readonly UnresolvedPart[];
};

export type SourcingVariant = Omit<SourcingPreview, "price_snapshot_id"> & {
  readonly optimized_scenario: Scenario;
  readonly savings: Money;
};

/** Une nomenclature au choix : le Multipla ou l'une des trois Valhalla. */
export interface BomVersion {
  id: string;
  label: string;
  root_part_ref: string;
  part_count: number;
  edge_count: number;
  /** null tant que la version n'a pas passé ses contrôles : elle ne s'ouvre pas. */
  validated_at: string | null;
  is_synthetic: boolean;
  /** Taux horaire proposé à la création d'un scénario, ou null s'il est inconnu. */
  reference_labour_rate: string | null;
  /** Absent (et non null) quand la version n'est pas une variante de carrosserie. */
  parent_version_id?: string;
}

/** Un snapshot de prix enregistré, tel que la liste le résume. */
export interface PriceSnapshotSummary {
  id: string;
  taken_at: string;
  source: string;
  currency: string;
  bom_version: string | null;
  status: "FRESH" | "STALE" | "DEGRADED";
  age_seconds: number;
  counts: { prices: number; fallback: number; quarantined: number; missing: number };
}

export interface SupplierPlant {
  plant_id: string;
  label: string;
  origin_country: string;
  price_coefficient: string;
  lead_time_days: number;
  transport_co2_kg_per_kg: string;
  is_default: boolean;
}

/** Un fournisseur qui vend au moins une pièce de la nomenclature ouverte. */
export interface SupplierSummary {
  supplier_id: string;
  name: string;
  part_count: number;
  /** Pièces pour lesquelles il est le fournisseur retenu par défaut. */
  default_count: number;
  plants: SupplierPlant[];
}

export interface SuppliedPart {
  part_ref: string;
  label: string;
  unit: string;
  system: string;
  price_multiplier: string;
  is_default: boolean;
  /** Prix du dernier snapshot de la nomenclature, ou null s'il n'en a pas. */
  reference_price: Money | null;
}

export interface SupplierParts {
  supplier_id: string;
  name: string;
  plants: SupplierPlant[];
  price_snapshot: { id: string; taken_at: string; currency: string } | null;
  items: SuppliedPart[];
}

/** L'année de marché simulée d'une pièce, et ses prix figés. */
export interface PriceHistoryResponse {
  part_ref: string;
  label: string;
  unit: string;
  currency: string;
  profile: string | null;
  drivers: Record<string, string>;
  origin_currency: string | null;
  reference: string;
  points: { date: string; price: string }[];
  now: { at: string; price: string };
  snapshots: { id: string; taken_at: string; price: string; origin: string }[];
  is_synthetic: boolean;
}

/** Une pièce de carrosserie modifiée ou nouvelle, avec ses écarts déjà calculés par l'API. */
export interface PartChange {
  part_ref: string;
  label: string;
  kind: "MODIFIED" | "NEW";
  material_before: string | null;
  material_after: string;
  mass_before_kg: string | null;
  mass_after_kg: string;
  mass_delta_kg: string;
  cumulative_quantity: string;
  /** Montants nus : la devise est celle de `cost`. `null` sans prix, ou pour une pièce nouvelle (avant). */
  unit_cost_before: string | null;
  unit_cost_after: string | null;
}

/** `null` sans snapshot de prix : `cost_status` vaut alors `NO_PRICES`. */
export interface BodyCost {
  snapshot_id: string;
  total_before: Money;
  total_after: Money;
  delta: Money;
}

export interface BodyChanges {
  version: string;
  parent_version: string | null;
  changes: PartChange[];
  cost: BodyCost | null;
  cost_status: "OK" | "NO_PRICES";
  material_mass_delta_kg: string;
}

export interface BodyImportResult extends Omit<BodyChanges, "version"> {
  status: "CREATED" | "ALREADY_IMPORTED" | "NO_CHANGE";
  message: string;
  variant: { id: string; label: string } | null;
  scenario_id: string | null;
}

export interface ImportFault {
  code: string;
  message: string;
  object: string;
  part_ref: string | null;
}

/** La fiche d'une pièce ; les clés de calcul n'existent qu'avec `calculation_id`. */
export interface PartCardData {
  part_ref: string;
  label: string;
  material_ref: string | null;
  material_quantity_kg: string | null;
  mass_kg: string | null;
  composition: { part_ref: string; label: string; quantity: string; unit: string }[];
  cumulative_quantity?: string | null;
  unit_cost?: Money | null;
  own_unit_cost?: Money | null;
  own_contribution?: Money | null;
}
