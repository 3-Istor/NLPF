import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Scenario } from "../api/types";
import { AfterSalesToggle } from "./AfterSalesToggle";

const base: Scenario = {
  id: "scn-1",
  name: "Base",
  bom_version: "bom-valhalla-hybride-2026-10-02",
  display_currency: "EUR",
  labour_rate: "60.00",
  active_rules: ["labour"],
  parameters: [],
  calculation_state: "UP_TO_DATE",
  stale_reason: null,
  last_calculation_id: "calc-1",
  include_after_sales: false,
  after_sales_available: true,
};

describe("AfterSalesToggle", () => {
  it("bascule le réglage sans rien calculer", () => {
    const onChange = vi.fn();
    render(<AfterSalesToggle scenario={base} frozen={false} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText(/Inclure le SAV/));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("est grisé et le dit quand la nomenclature n'a aucun SAV", () => {
    render(
      <AfterSalesToggle
        scenario={{ ...base, after_sales_available: false }}
        frozen={false}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText(/Inclure le SAV/)).toBeDisabled();
    expect(screen.getByText("(aucun)")).toBeInTheDocument();
  });

  it("ne se modifie pas sur un calcul figé", () => {
    render(<AfterSalesToggle scenario={base} frozen onChange={vi.fn()} />);
    expect(screen.getByLabelText(/Inclure le SAV/)).toBeDisabled();
  });
});
