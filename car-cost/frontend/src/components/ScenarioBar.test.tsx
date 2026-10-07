/**
 * Figer sous un nom : le nom est obligatoire, proposé, rogné ; la liste ouvre.
 * Le scénario sans réglage reste toujours atteignable depuis la liste, même
 * quand tous les scénarios existants portent des réglages.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CalculationSnapshotSummary, Scenario } from "../api/types";
import { ScenarioBar } from "./ScenarioBar";

const base: Scenario = {
  id: "scn-1",
  name: "Base",
  bom_version: "v1",
  display_currency: "EUR",
  labour_rate: "42.00",
  active_rules: [],
  parameters: [],
  calculation_state: "UP_TO_DATE",
  stale_reason: null,
  last_calculation_id: "calc-1",
};

const tuned: Scenario = {
  ...base,
  id: "scn-tuned",
  name: "Variante fournisseur",
  active_rules: ["labour"],
  parameters: [
    {
      parameter_id: "prm-1",
      part_ref: "ALT-BEARING",
      scope: "part",
      path: null,
      supplier_id: "sup-1",
      plant_id: null,
      price_override: null,
      price_override_justification: null,
    },
  ],
  calculation_state: "NEVER_RUN",
  last_calculation_id: null,
};

function snapshot(id: string, name: string): CalculationSnapshotSummary {
  return {
    id,
    name,
    bom_version: "v1",
    scenario_id: "scn-1",
    scenario_name: "Base",
    calculation_id: `calc-${id}`,
    price_snapshot_id: "snp-1",
    created_at: "2026-10-01T12:00:00+00:00",
  };
}

function bar(overrides: Partial<React.ComponentProps<typeof ScenarioBar>> = {}) {
  const props = {
    scenarios: [base],
    current: base,
    onSelect: vi.fn(),
    onSelectBlank: vi.fn(),
    onDuplicate: vi.fn(),
    onDelete: vi.fn(),
    onOpenDecision: vi.fn(),
    snapshots: [],
    openSnapshotId: null,
    onFreeze: vi.fn(),
    onOpenSnapshot: vi.fn(),
    ...overrides,
  };
  render(<ScenarioBar {...props} />);
  return props;
}

const openForm = () =>
  fireEvent.click(screen.getByRole("button", { name: "Figer sous un nom" }));
const field = () => screen.getByLabelText("Nom du snapshot de calcul");

afterEach(() => vi.useRealTimers());

describe("figer sous un nom", () => {
  it("le champ s'ouvre vide : aucun nom n'est proposé à la place de l'utilisateur", () => {
    bar();

    openForm();

    expect(field()).toHaveValue("");
    expect(field()).toHaveAttribute("placeholder", "Nom du snapshot (obligatoire)");
  });

  it("un snapshot ouvert : le bouton dit qu'il fige le scénario vivant", () => {
    bar({ openSnapshotId: "csn-1" });

    expect(screen.queryByRole("button", { name: "Figer sous un nom" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Figer le scénario vivant" }));
    expect(field()).toHaveValue("");
  });

  it("dupliquer s'ouvre aussi sur un champ vide", () => {
    bar();

    fireEvent.click(screen.getByRole("button", { name: "Dupliquer" }));

    expect(screen.getByLabelText("Nom de la copie")).toHaveValue("");
  });

  it("le nom saisi est envoyé, rogné", () => {
    const props = bar();
    openForm();

    fireEvent.change(field(), { target: { value: "  Référence T3 " } });
    fireEvent.click(screen.getByRole("button", { name: "Figer" }));

    expect(props.onFreeze).toHaveBeenCalledWith("Référence T3");
  });

  it("le nom est obligatoire", () => {
    const props = bar();
    openForm();

    fireEvent.change(field(), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Figer" }));

    expect(props.onFreeze).not.toHaveBeenCalled();
    expect(screen.getByText("Le nom est obligatoire.")).toBeInTheDocument();
  });

  it("la liste montre les noms et ouvre le snapshot choisi", () => {
    const props = bar({
      snapshots: [snapshot("csn-1", "Référence T3"), snapshot("csn-2", "Variante Turquie")],
    });
    const list = screen.getByLabelText("Snapshots de calcul");
    expect(list).toHaveTextContent("Référence T3");
    expect(list).toHaveTextContent("Variante Turquie");

    fireEvent.change(list, { target: { value: "csn-2" } });

    expect(props.onOpenSnapshot).toHaveBeenCalledWith("csn-2");
  });
});

describe("le scénario sans réglage", () => {
  it("est proposé même si aucun n'existe", () => {
    bar({ scenarios: [tuned], current: tuned });
    expect(
      screen.getByRole("option", { name: "Catalogue sans réglage" }),
    ).toBeInTheDocument();
  });

  it("le choisir demande le scénario vierge, pas un identifiant", () => {
    const props = bar({ scenarios: [tuned], current: tuned });
    fireEvent.change(screen.getByLabelText("Scénario"), { target: { value: "" } });
    expect(props.onSelectBlank).toHaveBeenCalledOnce();
    expect(props.onSelect).not.toHaveBeenCalled();
  });
});
