/**
 * La vue « où est-elle montée ? » : l'échec et la liste partielle se disent.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { WhereUsed } from "./WhereUsed";

function page(count: number, total: number) {
  return {
    part_ref: "BOLT-M8",
    occurrence_count: total,
    total,
    items: Array.from({ length: count }, (_, index) => ({
      path: `root/n${index}/BOLT-M8`,
      path_labels: ["Véhicule", `Sous-ensemble ${index}`, "Boulon"],
      quantity_on_path: "4",
    })),
  };
}

function mount() {
  return render(<WhereUsed version="bom-test" partRef="BOLT-M8" onClose={() => {}} />);
}

afterEach(() => vi.restoreAllMocks());

describe("emplacements de montage", () => {
  it("affiche l'erreur au lieu de charger à vie", async () => {
    vi.spyOn(api, "whereUsed").mockRejectedValue(new Error("réseau coupé"));
    mount();

    expect(await screen.findByRole("alert")).toHaveTextContent("réseau coupé");
    expect(screen.queryByText("chargement…")).not.toBeInTheDocument();
  });

  it("dit quand la liste est partielle", async () => {
    vi.spyOn(api, "whereUsed").mockResolvedValue(page(2, 5) as never);
    mount();

    expect(await screen.findByText(/2 emplacements sur 5/)).toBeInTheDocument();
  });

  it("ne dit rien de plus quand tout est là", async () => {
    vi.spyOn(api, "whereUsed").mockResolvedValue(page(2, 2) as never);
    mount();

    await screen.findAllByRole("listitem");
    expect(screen.queryByText(/sur 2/)).not.toBeInTheDocument();
  });
});
