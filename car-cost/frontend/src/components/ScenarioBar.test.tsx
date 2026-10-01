/**
 * Le scénario sans réglage reste toujours atteignable depuis la liste, même
 * quand tous les scénarios existants portent des réglages.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Scenario } from "../api/types";
import { ScenarioBar } from "./ScenarioBar";

const tuned: Scenario = {
  id: "scn-tuned",
  name: "Variante fournisseur",
  bom_version: "bom-test",
  display_currency: "EUR",
  labour_rate: "42.00",
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
  stale_reason: null,
  last_calculation_id: null,
};

function renderBar() {
  const onSelect = vi.fn();
  const onSelectBlank = vi.fn();
  render(
    <ScenarioBar
      scenarios={[tuned]}
      current={tuned}
      onSelect={onSelect}
      onSelectBlank={onSelectBlank}
      onDuplicate={vi.fn()}
      onDelete={vi.fn()}
      onOpenDecision={vi.fn()}
    />,
  );
  return { onSelect, onSelectBlank, select: screen.getByLabelText("Scénario") };
}

describe("ScenarioBar", () => {
  it("propose un scénario sans réglage même si aucun n'existe", () => {
    renderBar();
    expect(
      screen.getByRole("option", { name: "Catalogue — sans réglage" }),
    ).toBeInTheDocument();
  });

  it("choisir cette entrée demande le scénario vierge, pas un identifiant", () => {
    const { onSelect, onSelectBlank, select } = renderBar();
    fireEvent.change(select, { target: { value: "" } });
    expect(onSelectBlank).toHaveBeenCalledOnce();
    expect(onSelect).not.toHaveBeenCalled();
  });
});
