/**
 * L'aide à la décision peut mentir sans se voir de trois façons : afficher un
 * CO₂ nul au lieu d'inconnu, taire une pièce que la contrainte n'a pas pu
 * corriger, et créer la variante avec d'autres lignes — ou un autre snapshot —
 * que celles que l'utilisateur a vues.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CalculationSnapshotSummary,
  Comparison,
  Scenario,
  SourcingPreview,
} from "../api/types";
import { ApiFailure } from "../api/client";
import { DecisionDialog } from "./DecisionDialog";

const compare = vi.fn();
const previewSourcing = vi.fn();
const createSourcingVariant = vi.fn();
const calculationSnapshots = vi.fn();
const compareCalculationSnapshots = vi.fn();

vi.mock("../api/client", () => ({
  ApiFailure: class extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.code = code;
      this.status = status;
    }
  },
  api: {
    calculationSnapshots: (...args: unknown[]) => calculationSnapshots(...args),
    compareCalculationSnapshots: (...args: unknown[]) =>
      compareCalculationSnapshots(...args),
    compare: (...args: unknown[]) => compare(...args),
    previewSourcing: (...args: unknown[]) => previewSourcing(...args),
    createSourcingVariant: (...args: unknown[]) => createSourcingVariant(...args),
  },
}));

function scenario(id: string, name: string): Scenario {
  return {
    id,
    name,
    bom_version: "bom-test",
    display_currency: "EUR",
    labour_rate: "42.00",
    active_rules: ["labour"],
    parameters: [],
    calculation_state: "NEVER_RUN",
    stale_reason: null,
    last_calculation_id: null,
  };
}

const base = scenario("scn-a", "Base");
const variant = scenario("scn-b", "Turquie");

const euros = (amount: string) => ({ amount, currency: "EUR" });

const comparison: Comparison = {
  calculation_a_id: "calc-a",
  calculation_b_id: "calc-b",
  price_snapshot_id: "snp-jour",
  total_a: euros("395.000000"),
  total_b: euros("372.000000"),
  cost_delta: euros("-23.000000"),
  co2_delta_kg: null,
  top_differences: [
    {
      part_ref: "S",
      contribution_a: euros("230.000000"),
      contribution_b: euros("207.000000"),
      delta: euros("-23.000000"),
      cumulative_quantity_a: "23.000000",
      cumulative_quantity_b: "23.000000",
    },
  ],
};

const preview: SourcingPreview = {
  base_scenario_id: "scn-a",
  price_snapshot_id: "snp-apercu",
  constraints: { forbidden_origins: ["RU"], max_lead_time_days: null },
  recommendations: [
    {
      part_ref: "S",
      accepted: false,
      required_by_constraint: false,
      current: { supplier_id: "SUP-IT", plant_id: "PLT-IT", origin_country: "IT", unit_price: euros("10.000000") },
      recommended: { supplier_id: "SUP-IT", plant_id: "PLT-TR", origin_country: "TR", lead_time_days: 12, unit_price: euros("9.000000") },
      affected_quantity: "23.000000",
      estimated_saving: euros("23.000000"),
    },
    {
      part_ref: "T",
      accepted: false,
      required_by_constraint: true,
      current: { supplier_id: "SUP-RU", plant_id: "PLT-RU", origin_country: "RU", unit_price: euros("2.000000") },
      recommended: { supplier_id: "SUP-DE", plant_id: "PLT-DE", origin_country: "DE", lead_time_days: 4, unit_price: euros("3.000000") },
      affected_quantity: "4.000000",
      estimated_saving: euros("-4.000000"),
    },
  ],
  unresolved: [
    {
      part_ref: "U",
      current: { supplier_id: "SUP-RU", plant_id: "PLT-RU", origin_country: "RU" },
      reason: "aucune option autorisée",
    },
  ],
};

function mount() {
  const callbacks = {
    onClose: vi.fn(),
    onGoToPart: vi.fn(),
    onCreated: vi.fn(),
    onOpenScenario: vi.fn(),
  };
  render(
    <DecisionDialog
      scenarios={[base, variant]}
      current={base}
      bomVersion="bom-test"
      {...callbacks}
    />,
  );
  return callbacks;
}

function frozen(id: string, name: string): CalculationSnapshotSummary {
  return {
    id,
    name,
    bom_version: "bom-test",
    scenario_id: "scn-a",
    scenario_name: "Base",
    calculation_id: `calc-${id}`,
    price_snapshot_id: "snp-jour",
    created_at: "2026-10-01T10:00:00Z",
  };
}

const frozenPair = [frozen("csn-1", "Référence T3"), frozen("csn-2", "Variante Turquie")];

beforeEach(() => {
  calculationSnapshots
    .mockReset()
    .mockResolvedValue({ items: frozenPair, total: 2 });
  compareCalculationSnapshots.mockReset().mockResolvedValue({
    ...comparison,
    snapshot_a: { id: "csn-1", name: "Référence T3" },
    snapshot_b: { id: "csn-2", name: "Variante Turquie" },
  });
  compare.mockReset().mockResolvedValue(comparison);
  previewSourcing.mockReset().mockResolvedValue(preview);
  createSourcingVariant.mockReset().mockResolvedValue({
    ...preview,
    optimized_scenario: scenario("scn-c", "Base — sourcing optimisé"),
    savings: euros("23.000000"),
  });
});

describe("comparer", () => {
  it("affiche l'écart servi par l'API, et le CO₂ comme inconnu", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Comparer" }));

    expect(await screen.findByText("Écart B − A")).toBeInTheDocument();
    expect(compare).toHaveBeenCalledWith("scn-a", "scn-b");
    expect(screen.getByText("non calculé")).toBeInTheDocument();
    expect(screen.queryByText(/0,00 kg/)).not.toBeInTheDocument();
    expect(screen.getAllByText("-23,00 €").length).toBeGreaterThan(0);
  });

  it("mène à la pièce depuis un écart", async () => {
    const { onGoToPart } = mount();
    fireEvent.click(screen.getByRole("button", { name: "Comparer" }));

    fireEvent.click(await screen.findByRole("button", { name: "S" }));

    expect(onGoToPart).toHaveBeenCalledWith("S");
  });
});

describe("recommander", () => {
  async function evaluate() {
    const callbacks = mount();
    fireEvent.click(screen.getByRole("button", { name: "Recommander un sourcing" }));
    fireEvent.change(screen.getByPlaceholderText("ex. RU, TR"), {
      target: { value: "ru" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Évaluer" }));
    await screen.findByText(/2 recommandation\(s\)/);
    return callbacks;
  }

  it("nomme les pièces que la contrainte n'a pas pu corriger", async () => {
    await evaluate();

    expect(previewSourcing).toHaveBeenCalledWith("scn-a", {
      forbidden_origins: ["ru"],
      max_lead_time_days: null,
    });
    expect(screen.getByText(/violent une contrainte/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "U" })).toBeInTheDocument();
    expect(screen.getByText("imposé")).toBeInTheDocument();
  });

  it("crée la variante avec les seules lignes cochées, sur le snapshot vu", async () => {
    const { onCreated } = await evaluate();

    fireEvent.click(screen.getByRole("checkbox", { name: "Appliquer T" }));
    fireEvent.click(screen.getByRole("button", { name: /Créer la variante \(1 ligne/ }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(createSourcingVariant).toHaveBeenCalledWith("scn-a", {
      forbidden_origins: ["RU"],
      max_lead_time_days: null,
      name: "Base — sourcing optimisé",
      accepted_part_refs: ["S"],
      price_snapshot_id: "snp-apercu",
    });
    expect(screen.getByText(/Le scénario d'origine n'a pas été modifié/)).toBeInTheDocument();
  });
});

describe("comparer deux snapshots de calcul", () => {
  async function openTab() {
    const callbacks = mount();
    fireEvent.click(
      screen.getByRole("button", { name: "Comparer deux snapshots de calcul" }),
    );
    return callbacks;
  }

  it("compare deux snapshots de calcul par leur nom, sans recalcul", async () => {
    await openTab();
    await screen.findAllByRole("option", { name: /Variante Turquie/ });
    fireEvent.change(screen.getByLabelText("A — référence"), {
      target: { value: "csn-1" },
    });
    fireEvent.change(screen.getByLabelText("B — variante"), {
      target: { value: "csn-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Comparer" }));

    expect(await screen.findByText("Écart B − A")).toBeInTheDocument();
    expect(compareCalculationSnapshots).toHaveBeenCalledWith("csn-1", "csn-2");
    expect(compare).not.toHaveBeenCalled();
    const terms = screen.getAllByRole("term").map((node) => node.textContent);
    expect(terms).toContain("Référence T3");
    expect(terms).toContain("Variante Turquie");
    expect(screen.getAllByText("-23,00 €").length).toBeGreaterThan(0);
  });

  it("explique un refus", async () => {
    compareCalculationSnapshots.mockRejectedValue(
      new ApiFailure(
        "INCOMPARABLE_SCENARIOS",
        "les scénarios doivent être calculés avec le même snapshot de prix",
        422,
      ),
    );
    await openTab();
    await screen.findAllByRole("option", { name: /Variante Turquie/ });
    fireEvent.click(screen.getByRole("button", { name: "Comparer" }));

    expect(
      await screen.findByText(/doivent être calculés avec le même snapshot de prix/),
    ).toBeInTheDocument();
  });

  it("demande deux snapshots quand il n'y en a qu'un", async () => {
    calculationSnapshots.mockResolvedValue({ items: [frozenPair[0]], total: 1 });
    await openTab();

    expect(
      await screen.findByText("Il faut au moins deux snapshots de calcul."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Comparer" })).toBeDisabled();
  });

  it("dit sur quels prix porte le snapshot", async () => {
    await openTab();

    const options = await screen.findAllByRole("option", {
      name: /Référence T3.*prix snp-jour/,
    });
    expect(options.length).toBeGreaterThan(0);
  });
});
