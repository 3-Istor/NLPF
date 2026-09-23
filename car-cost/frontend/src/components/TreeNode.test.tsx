/**
 * Les deux comportements de l'arbre qui peuvent être faux sans se voir :
 * le dépliage doit demander les enfants directs, et seulement eux ; et l'écran
 * ne doit additionner aucun montant.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Page, TreeLine } from "../api/types";
import { TreeNode } from "./TreeNode";

const calls: string[] = [];

vi.mock("../api/client", () => ({
  ApiFailure: class extends Error {},
  api: {
    children: async (_version: string, path: string): Promise<Page<TreeLine>> => {
      calls.push(path);
      return {
        items: path === "V" ? [child("V/A", "A"), child("V/B", "B")] : [],
        total: path === "V" ? 2 : 0,
        limit: 50,
        offset: 0,
      };
    },
    part: async () => ({ suppliers: [] }),
  },
}));

function line(overrides: Partial<TreeLine> = {}): TreeLine {
  return {
    path: "V",
    part_ref: "V",
    label: "Véhicule complet",
    system: "VEH",
    valuation_mode: "manufactured",
    unit: "pce",
    edge_quantity: "1.000000",
    has_children: true,
    child_count: 2,
    parent_count: 0,
    occurrence_count: 1,
    ...overrides,
  };
}

const LABELS: Record<string, string> = {
  A: "Groupe motopropulseur",
  B: "Châssis",
};

function child(path: string, ref: string): TreeLine {
  // Libellé et référence distincts : sinon une recherche par texte trouve les
  // deux, et le test échoue pour une raison qui n'est pas celle qu'il teste.
  return line({
    path,
    part_ref: ref,
    label: LABELS[ref],
    has_children: true,
    child_count: 3,
    occurrence_count: 1,
  });
}

function mount(overrides: Partial<TreeLine> = {}) {
  return render(
    <ul>
      <TreeNode
        line={line(overrides)}
        version="bom-test"
        scenarioId={null}
        calculationId={null}
        depth={0}
        onParameterChanged={() => {}}
        onShowWhereUsed={() => {}}
      />
    </ul>,
  );
}

beforeEach(() => {
  calls.length = 0;
});

describe("dépliage", () => {
  it("ne charge rien tant qu'on n'a pas déplié", () => {
    mount();

    expect(calls).toEqual([]);
  });

  it("demande les enfants directs du nœud, et rien au-delà", async () => {
    const { getByLabelText } = mount();

    getByLabelText("Déplier").click();

    await waitFor(() => expect(screen.getByText("Groupe motopropulseur")).toBeInTheDocument());
    // Un seul appel, sur le nœud ouvert : les petits-enfants ne sont pas
    // demandés tant qu'on ne les ouvre pas.
    expect(calls).toEqual(["V"]);
  });

  it("ne redemande pas les enfants déjà chargés", async () => {
    const { container } = mount();
    // Le chevron de la racine, pas ceux des enfants : une fois ouverts, ils
    // portent le même libellé accessible.
    const chevron = () =>
      container.querySelector("button.chevron") as HTMLButtonElement;

    chevron().click();
    await waitFor(() =>
      expect(screen.getByText("Groupe motopropulseur")).toBeInTheDocument(),
    );

    chevron().click();
    await waitFor(() =>
      expect(screen.queryByText("Groupe motopropulseur")).not.toBeInTheDocument(),
    );

    chevron().click();
    await waitFor(() =>
      expect(screen.getByText("Groupe motopropulseur")).toBeInTheDocument(),
    );

    expect(calls).toEqual(["V"]);
  });
});

describe("pièce partagée", () => {
  it("porte son compte d'emplacements", () => {
    mount({ occurrence_count: 12 });

    expect(screen.getByText("utilisée à 12 endroits")).toBeInTheDocument();
  });

  it("n'affiche pas de badge quand elle n'est montée qu'une fois", () => {
    mount({ occurrence_count: 1 });

    expect(screen.queryByText(/utilisée à/)).not.toBeInTheDocument();
  });
});

describe("montants", () => {
  it("affiche des tirets tant qu'aucun calcul n'a eu lieu", () => {
    const { container } = mount();

    expect(container.querySelectorAll(".cost")[0].textContent).toBe("—");
  });

  it("affiche le montant reçu, sans jamais en calculer un", () => {
    mount({
      unit_cost: { amount: "412.550000", currency: "EUR" },
      rolled_up_contribution: { amount: "825.100000", currency: "EUR" },
    });

    expect(screen.getByText("412,55 €")).toBeInTheDocument();
    expect(screen.getByText("825,10 €")).toBeInTheDocument();
  });
});
