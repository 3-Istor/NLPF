/**
 * La fiche d'une pièce : trois réponses de l'API assemblées, aucune opération.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PartCardData, PartChange, TreeLine } from "../api/types";
import { mass, money } from "../format";
import { PartCard } from "./PartCard";

const eur = (amount: string) => ({ amount, currency: "EUR" });

const spoilerLine: TreeLine = {
  path: "V/BODY-SPOILER",
  part_ref: "BODY-SPOILER",
  label: "Aileron",
  system: "CAR",
  valuation_mode: "manufactured",
  unit: "pce",
  edge_quantity: "1.000000",
  has_children: true,
  child_count: 2,
  parent_count: 1,
  occurrence_count: 1,
};

const spoiler: PartCardData = {
  part_ref: "BODY-SPOILER",
  label: "Aileron",
  material_ref: "MAT-ABS-GRANULE",
  material_quantity_kg: "3.150000",
  mass_kg: "3.150000",
  composition: [
    { part_ref: "FIX-M8-20", label: "Vis M8", quantity: "4", unit: "pce" },
    { part_ref: "MAT-ABS-GRANULE", label: "Granulé ABS", quantity: "3.150000", unit: "kg" },
  ],
  cumulative_quantity: "1",
  unit_cost: eur("6.523386200000"),
  own_unit_cost: eur("5.100000000000"),
  own_contribution: eur("6.523386200000"),
};

const doorLine: TreeLine = { ...spoilerLine, path: "V/DOOR", part_ref: "CAR-DOOR-SHELL-FRONT", label: "Porte avant", edge_quantity: "2.000000" };

const door: PartCardData = {
  ...spoiler,
  part_ref: "CAR-DOOR-SHELL-FRONT",
  label: "Porte avant",
  material_ref: "MAT-ALU-SHEET",
  material_quantity_kg: "3.233121",
  mass_kg: "3.233121",
  composition: [],
  cumulative_quantity: "2",
  unit_cost: eur("23.483303222933"),
  own_contribution: eur("46.966606445866"),
};

const doorChange: PartChange = {
  part_ref: "CAR-DOOR-SHELL-FRONT",
  label: "Porte avant",
  kind: "MODIFIED",
  material_before: "MAT-STEEL-SHEET",
  material_after: "MAT-ALU-SHEET",
  mass_before_kg: "9.400000",
  mass_after_kg: "3.233121",
  mass_delta_kg: "-6.166879",
  cumulative_quantity: "2",
  unit_cost_before: "24.602194200000",
  unit_cost_after: "23.483303222933",
};

describe("la fiche pièce", () => {
  it("shows the spoiler as a BOM part", () => {
    const change: PartChange = {
      ...doorChange,
      part_ref: "BODY-SPOILER",
      kind: "NEW",
      material_before: null,
      mass_before_kg: null,
      unit_cost_before: null,
    };
    render(<PartCard card={spoiler} line={spoilerLine} change={change} />);

    expect(screen.getAllByText("MAT-ABS-GRANULE").length).toBeGreaterThan(0);
    expect(screen.getAllByText(mass("3.150000")).length).toBeGreaterThan(0);
    const screw = screen.getByText("FIX-M8-20").closest("li")!;
    expect(within(screw).getByText(/4/)).toBeInTheDocument();
    expect(screen.getAllByText(money(spoiler.unit_cost)).length).toBeGreaterThan(0);
    expect(money(spoiler.unit_cost)).toContain("6,52");
    expect(screen.getByText(/nouvelle pièce/)).toBeInTheDocument();
    expect(screen.getByText("Aileron")).toBeInTheDocument();
  });

  it("shows before and after for an aluminium door", () => {
    render(<PartCard card={door} line={doorLine} change={doorChange} />);

    for (const text of [
      "MAT-STEEL-SHEET",
      mass("9.400000"),
      money(eur("24.602194200000")),
      money(eur("23.483303222933")),
      mass("3.233121"),
    ]) {
      expect(screen.getAllByText(text).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByText("MAT-ALU-SHEET").length).toBeGreaterThan(0);
  });

  it("shows no before-after on the original vehicle", () => {
    render(<PartCard card={door} line={doorLine} />);

    expect(screen.queryByText("Avant → après")).toBeNull();
    expect(screen.queryByText(/nouvelle pièce/)).toBeNull();
  });

  it("never computes", () => {
    // 3 × 10,00 ne fait pas 7,00 : la fiche affiche ce que l'API a servi.
    const served = { ...door, cumulative_quantity: "3", unit_cost: eur("10.00"), own_contribution: eur("7.00") };
    render(<PartCard card={served} line={doorLine} />);

    expect(screen.getByText(money(eur("7.00")))).toBeInTheDocument();
    expect(screen.queryByText(money(eur("30.00")))).toBeNull();
  });

  it("reads the unit quantity from the tree line", () => {
    render(<PartCard card={door} line={doorLine} />);

    expect(screen.getByText(/× 2/)).toBeInTheDocument();
  });
});
