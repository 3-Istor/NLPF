/**
 * Le panneau « Variante » : ce que l'API sert, rien de recalculé.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiFailure } from "../api/client";
import type { BodyChanges, PartChange } from "../api/types";
import { mass, money } from "../format";
import { BodyChangesPanel } from "./BodyChangesPanel";

const hood: PartChange = {
  part_ref: "CAR-HOOD-SHELL",
  label: "Capot",
  kind: "MODIFIED",
  material_before: "MAT-STEEL-SHEET",
  material_after: "MAT-ALU-SHEET",
  mass_before_kg: "11.200000",
  mass_after_kg: "3.852229",
  mass_delta_kg: "-7.347771",
  cumulative_quantity: "1",
  unit_cost_before: "23.832401600000",
  unit_cost_after: "22.499254092617",
};

const delta = { amount: "-1.333147507383", currency: "EUR" };

const served: BodyChanges = {
  version: "bom-multipla-2026-09-22+1a2b3c4d",
  parent_version: "bom-multipla-2026-09-22",
  changes: [hood],
  cost: {
    snapshot_id: "snp-1",
    total_before: { amount: "5000.000000000000", currency: "EUR" },
    total_after: { amount: "4998.666852492617", currency: "EUR" },
    delta,
  },
  cost_status: "OK",
  material_mass_delta_kg: "-45.923567",
};

const mount = (changes: BodyChanges | null, failure: unknown = null) =>
  render(<BodyChangesPanel changes={changes} outcome={null} failure={failure} onOpen={() => {}} />);

describe("l'écart d'une variante", () => {
  it("shows the cost delta and masses as served", () => {
    mount(served);

    expect(screen.getByText(money(delta))).toBeInTheDocument();
    expect(money(delta)).toContain("1,33");
    expect(screen.getByText(mass("-7.347771"))).toBeInTheDocument();
    expect(mass("-7.347771")).toMatch(/7,35.*kg/);
    expect(screen.getByText("CAR-HOOD-SHELL")).toBeInTheDocument();
    expect(screen.getByText(mass("11.200000"))).toBeInTheDocument();
    expect(screen.getByText(mass("3.852229"))).toBeInTheDocument();
  });

  it("shows the total material mass delta", () => {
    mount(served);

    expect(screen.getByText(mass("-45.923567"))).toBeInTheDocument();
    expect(mass("-45.923567")).toContain("45,92");
  });

  it("says prices are unavailable instead of zero", () => {
    mount({ ...served, cost: null, cost_status: "NO_PRICES" });

    expect(screen.getByText(/prix indisponibles/)).toBeInTheDocument();
    expect(screen.queryByText(/0,00 €/)).toBeNull();
  });

  it("lists all import faults with their object", () => {
    const failure = new ApiFailure("BODY_IMPORT_REJECTED", "fichier refusé", 422, {
      faults: [
        { code: "MESH_NOT_CLOSED", message: "maillage ouvert", object: "Capot.001", part_ref: null },
        { code: "UNKNOWN_PART", message: "pièce inconnue", object: "Aileron.002", part_ref: null },
      ],
    });
    mount(null, failure);

    for (const text of ["MESH_NOT_CLOSED", "Capot.001", "UNKNOWN_PART", "Aileron.002"]) {
      expect(screen.getByText(new RegExp(text))).toBeInTheDocument();
    }
  });

  it("names the outcome of an import that changes nothing", () => {
    render(
      <BodyChangesPanel
        changes={null}
        outcome={{ ...served, status: "NO_CHANGE", message: "aucun changement", variant: null, scenario_id: null }}
        failure={null}
        onOpen={() => {}}
      />,
    );

    expect(screen.getByText(/aucun changement/)).toBeInTheDocument();
  });
});
