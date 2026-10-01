/** Figer sous un nom : le nom est obligatoire, proposé, rogné ; la liste ouvre. */

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
  it("le nom proposé par défaut est le scénario et l'heure", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 1, 14, 5));
    bar();

    openForm();

    expect(field()).toHaveValue("Base — 01/10/2026 14:05");
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
