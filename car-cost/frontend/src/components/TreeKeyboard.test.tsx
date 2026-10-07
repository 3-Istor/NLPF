/**
 * L'arbre au clavier, selon le motif WAI-ARIA « tree » : une seule ligne
 * atteignable par Tab, les flèches pour parcourir, déplier et replier,
 * Entrée pour ouvrir le panneau de saisie.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Page, Scenario, TreeLine } from "../api/types";
import { useTreeState } from "../tree/useTreeState";
import { rowId, Tree } from "./Tree";

const calls: string[] = [];
const served = new Map<string, TreeLine[]>();

vi.mock("../api/client", () => ({
  ApiFailure: class extends Error {},
  api: {
    children: async (_version: string, path: string): Promise<Page<TreeLine>> => {
      calls.push(path);
      const items = served.get(path) ?? [];
      return { items, total: items.length, limit: 50, offset: 0 };
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

// Libellés distincts des références : une recherche par texte ne trouve
// que ce qu'elle vise.
const LABELS: Record<string, string> = {
  A: "Groupe motopropulseur",
  B: "Châssis",
  C: "Habitacle",
  X: "Vis de fixation",
};

function child(path: string, ref: string, hasChildren: boolean): TreeLine {
  return line({
    path,
    part_ref: ref,
    label: LABELS[ref],
    has_children: hasChildren,
    child_count: hasChildren ? 1 : 0,
  });
}

const scenario: Scenario = {
  id: "scn-1",
  name: "Scénario de test",
  bom_version: "bom-test",
  display_currency: "EUR",
  labour_rate: "42.00",
  active_rules: [],
  parameters: [],
  calculation_state: "NEVER_RUN",
  stale_reason: null,
  last_calculation_id: null,
};

function Harness() {
  const state = useTreeState({ version: "bom-test", calculationId: null });
  return (
    <Tree
      root={line()}
      state={state}
      version="bom-test"
      scenario={scenario}
      onParameterChanged={() => {}}
      onShowWhereUsed={() => {}}
    />
  );
}

const row = (path: string) => document.getElementById(rowId(path))!;

const press = (key: string) => fireEvent.keyDown(document.activeElement!, { key });

function focus(path: string) {
  act(() => row(path).focus());
}

async function expandWithMouse(path: string) {
  fireEvent.click(row(path).querySelector("button.chevron")!);
  await waitFor(() => expect(row(path)).toHaveAttribute("aria-expanded", "true"));
}

async function mountWithV() {
  render(<Harness />);
  await expandWithMouse("V");
  await waitFor(() => expect(document.getElementById(rowId("V/B"))).not.toBeNull());
}

beforeEach(() => {
  calls.length = 0;
  served.clear();
  served.set("V", [child("V/A", "A", true), child("V/B", "B", false)]);
  served.set("V/A", [child("V/A/X", "X", false)]);
  localStorage.clear();
});

describe("clavier de l'arbre", () => {
  it("les rôles et niveaux sont exposés", async () => {
    await mountWithV();

    const items = screen.getAllByRole("treeitem");
    expect(items.map((item) => item.getAttribute("aria-level"))).toEqual(["1", "2", "2"]);
    expect(row("V")).toHaveAttribute("aria-expanded", "true");
    expect(row("V/B")).not.toHaveAttribute("aria-expanded");
    expect(screen.getByRole("tree", { name: "Nomenclature" })).toBeInTheDocument();
    expect(screen.getAllByRole("group")).toHaveLength(1);
  });

  it("une seule ligne est atteignable par Tab", async () => {
    await mountWithV();

    const reachable = screen
      .getAllByRole("treeitem")
      .filter((item) => item.getAttribute("tabindex") === "0");
    expect(reachable).toEqual([row("V")]);
  });

  it("flèche bas et haut parcourent les lignes visibles", async () => {
    await mountWithV();
    focus("V");

    press("ArrowDown");
    expect(document.activeElement).toBe(row("V/A"));
    expect(row("V/A")).toHaveAttribute("aria-selected", "true");
    expect(row("V/A")).toHaveAttribute("tabindex", "0");
    expect(row("V")).toHaveAttribute("tabindex", "-1");

    press("ArrowUp");
    expect(document.activeElement).toBe(row("V"));
  });

  it("flèche droite déplie, puis descend", async () => {
    await mountWithV();
    focus("V");
    press("ArrowDown");
    expect(row("V/A")).toHaveAttribute("aria-expanded", "false");

    press("ArrowRight");
    await waitFor(() => expect(row("V/A")).toHaveAttribute("aria-expanded", "true"));
    expect(calls).toContain("V/A");
    await waitFor(() => expect(document.getElementById(rowId("V/A/X"))).not.toBeNull());

    press("ArrowRight");
    expect(document.activeElement).toBe(row("V/A/X"));
  });

  it("flèche gauche remonte, puis replie", async () => {
    await mountWithV();
    await expandWithMouse("V/A");
    await waitFor(() => expect(document.getElementById(rowId("V/A/X"))).not.toBeNull());
    focus("V/A/X");

    press("ArrowLeft");
    expect(document.activeElement).toBe(row("V/A"));
    expect(row("V/A")).toHaveAttribute("aria-expanded", "true");

    press("ArrowLeft");
    await waitFor(() => expect(row("V/A")).toHaveAttribute("aria-expanded", "false"));
    expect(document.getElementById(rowId("V/A/X"))).toBeNull();
  });

  it("Entrée ouvre le panneau de la ligne", async () => {
    await mountWithV();
    focus("V");
    press("ArrowDown");
    // Parcourir sélectionne sans ouvrir : le panneau attend Entrée.
    expect(screen.queryByText("Ensemble fabriqué : A")).toBeNull();

    press("Enter");
    expect(await screen.findByText("Ensemble fabriqué : A")).toBeInTheDocument();
  });

  it("étoile déplie les frères", async () => {
    served.set("V", [
      child("V/A", "A", true),
      child("V/B", "B", false),
      child("V/C", "C", true),
    ]);
    served.set("V/C", []);
    await mountWithV();
    focus("V/A");

    press("*");
    await waitFor(() => expect(row("V/A")).toHaveAttribute("aria-expanded", "true"));
    await waitFor(() => expect(row("V/C")).toHaveAttribute("aria-expanded", "true"));
    expect(row("V/B")).not.toHaveAttribute("aria-expanded");
    expect(calls).toEqual(["V", "V/A", "V/C"]);
  });

  it("rien ne bouge au bord", async () => {
    render(<Harness />);
    focus("V");
    expect(document.activeElement).toBe(row("V"));

    // ← sur la racine repliée : pas de parent, rien à replier.
    expect(() => press("ArrowLeft")).not.toThrow();
    expect(document.activeElement).toBe(row("V"));
    expect(row("V")).toHaveAttribute("aria-expanded", "false");

    await expandWithMouse("V");
    await waitFor(() => expect(document.getElementById(rowId("V/B"))).not.toBeNull());
    focus("V/B");
    const before = calls.length;

    // ↓ sur la dernière ligne visible.
    press("ArrowDown");
    expect(document.activeElement).toBe(row("V/B"));

    // → sur une feuille.
    press("ArrowRight");
    expect(document.activeElement).toBe(row("V/B"));
    expect(calls.length).toBe(before);
  });
});
