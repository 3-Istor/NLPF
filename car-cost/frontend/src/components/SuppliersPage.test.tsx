import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { SuppliersPage } from "./SuppliersPage";

vi.mock("../api/client", () => ({
  ApiFailure: class extends Error {},
  api: {
    suppliers: vi.fn(async () => ({
      items: [
        {
          supplier_id: "SUP-AML-TIER1",
          name: "Aston Martin / Tier-1 non publié",
          part_count: 2,
          default_count: 2,
          plants: [{ plant_id: "PLT-AML-GAYDON", label: "Gaydon", origin_country: "GB", price_coefficient: "1.000000", lead_time_days: 6, transport_co2_kg_per_kg: "0.004000", is_default: true }],
        },
        {
          supplier_id: "SUP-MIDLANDS-COMP",
          name: "Midlands Composites",
          part_count: 1,
          default_count: 0,
          plants: [],
        },
      ],
    })),
    supplierParts: vi.fn(async (_version: string, supplierId: string) => ({
      supplier_id: supplierId,
      name: supplierId === "SUP-AML-TIER1" ? "Aston Martin / Tier-1 non publié" : "Midlands Composites",
      plants: [],
      price_snapshot: { id: "snp-1", taken_at: "2026-10-02T09:00:00+00:00", currency: "EUR" },
      items:
        supplierId === "SUP-AML-TIER1"
          ? [
              { part_ref: "VALH-BOM-0006", label: "Monocoque carbone – cuve inférieure", unit: "pce", system: "CAR", price_multiplier: "1.000000", is_default: true, reference_price: { amount: "58554.000000", currency: "EUR" } },
              { part_ref: "VALH-BOM-0309", label: "Boîte DCT 8 rapports", unit: "pce", system: "TRN", price_multiplier: "1.000000", is_default: true, reference_price: null },
            ]
          : [
              { part_ref: "VALH-BOM-0006", label: "Monocoque carbone – cuve inférieure", unit: "pce", system: "CAR", price_multiplier: "1.071200", is_default: false, reference_price: null },
            ],
    })),
    priceHistory: vi.fn(async (_version: string, partRef: string) => ({
      part_ref: partRef,
      label: "Monocoque carbone – cuve inférieure",
      unit: "pce",
      currency: "EUR",
      profile: "composite",
      drivers: { energie: "0.65" },
      origin_currency: "GBP",
      reference: "58554.000000",
      points: [
        { date: "2025-12-31", price: "58554.000000" },
        { date: "2026-01-01", price: "60000.000000" },
        { date: "2026-01-02", price: "55000.000000" },
      ],
      now: { at: "2026-01-02T12:00:00+00:00", price: "57500.000000" },
      snapshots: [{ id: "snp-1", taken_at: "2026-10-02T09:00:00+00:00", price: "58554.000000", origin: "API" }],
      is_synthetic: true,
    })),
  },
}));

const VERSION = "bom-valhalla-hybride-2026-10-02";

beforeEach(() => {
  history.replaceState(null, "", "/");
  vi.clearAllMocks();
});

describe("SuppliersPage", () => {
  it("liste les fournisseurs et ouvre les pièces du premier", async () => {
    render(<SuppliersPage version={VERSION} />);
    expect(await screen.findByText("Midlands Composites")).toBeInTheDocument();
    expect(await screen.findByText("Boîte DCT 8 rapports")).toBeInTheDocument();
    expect(api.supplierParts).toHaveBeenCalledWith(VERSION, "SUP-AML-TIER1");
  });

  it("change de fournisseur et montre son multiplicateur", async () => {
    render(<SuppliersPage version={VERSION} />);
    fireEvent.click(await screen.findByText("Midlands Composites"));
    expect(await screen.findByText("× 1.071200")).toBeInTheDocument();
  });

  it("un clic sur une pièce affiche la courbe de son prix", async () => {
    render(<SuppliersPage version={VERSION} />);
    fireEvent.click(await screen.findByText("VALH-BOM-0309"));
    await waitFor(() => expect(api.priceHistory).toHaveBeenCalledWith(VERSION, "VALH-BOM-0309", "EUR"));
    const chart = await screen.findByRole("img");
    // Les douze mois qui finissent maintenant, sans légende « référence » sur l'axe.
    expect(within(chart).queryByText("référence")).not.toBeInTheDocument();
    expect(within(chart).getByText("janv.")).toBeInTheDocument();
    expect(chart.getAttribute("aria-label")).toMatch(/de 55 000,00 € à 60 000,00 €/);
    expect(new URLSearchParams(window.location.search).get("part")).toBe("VALH-BOM-0309");
    const facts = screen.getByText("Plus haut sur 12 mois").nextElementSibling as HTMLElement;
    expect(within(facts).getByText(/2026-01-01/)).toBeInTheDocument();
    const frozen = screen.getByRole("heading", { name: "Prix figés (snapshots)" })
      .parentElement as HTMLElement;
    expect(within(frozen).getByText("snp-1")).toBeInTheDocument();
  });

  it("filtre les pièces par référence ou libellé", async () => {
    render(<SuppliersPage version={VERSION} />);
    await screen.findByText("Boîte DCT 8 rapports");
    fireEvent.change(screen.getByLabelText("Filtrer les pièces"), { target: { value: "dct" } });
    expect(screen.queryByText("Monocoque carbone – cuve inférieure")).not.toBeInTheDocument();
    expect(screen.getByText("Boîte DCT 8 rapports")).toBeInTheDocument();
  });
});
