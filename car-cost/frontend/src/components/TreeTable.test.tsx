/**
 * L'arbre comme tableau : colonnes, en-tête, poids, et ce que dit chaque
 * nœud pendant qu'il charge, échoue ou ne montre qu'une partie de ses enfants.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Page, TreeLine } from "../api/types";
import { STORAGE_PREFIX, useTreeState } from "../tree/useTreeState";
import { rowId, Tree } from "./Tree";
import { TreeHeader } from "./TreeHeader";
import { TreeToolbar } from "./TreeToolbar";

type Handler = (path: string, calculationId: string | null) => Promise<Page<TreeLine>>;

const calls: string[] = [];
let handler: Handler;

vi.mock("../api/client", () => ({
  ApiFailure: class extends Error {},
  api: {
    children: (_version: string, path: string, calculationId: string | null) => {
      calls.push(path);
      return handler(path, calculationId);
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

const LABELS: Record<string, string> = { A: "Groupe motopropulseur", B: "Châssis", M: "Module" };

function child(path: string, ref: string, overrides: Partial<TreeLine> = {}): TreeLine {
  return line({ path, part_ref: ref, label: LABELS[ref], child_count: 1, ...overrides });
}

const page = (items: TreeLine[], total = items.length): Page<TreeLine> => ({
  items,
  total,
  limit: 50,
  offset: 0,
});

const defaultHandler: Handler = async (path) =>
  page(path === "V" ? [child("V/A", "A"), child("V/B", "B")] : []);

function Harness({ root, calculationId }: { root: TreeLine; calculationId: string | null }) {
  const state = useTreeState({ version: "bom-test", calculationId });
  return (
    <>
      <TreeToolbar onCollapseAll={state.collapseAll} />
      <TreeHeader />
      <Tree
        root={root}
        state={state}
        version="bom-test"
        scenario={null}
        onParameterChanged={() => {}}
        onShowWhereUsed={() => {}}
      />
    </>
  );
}

const mount = (root: TreeLine = line(), calculationId: string | null = null) => {
  const view = render(<Harness root={root} calculationId={calculationId} />);
  return {
    ...view,
    withCalculation: (id: string | null) =>
      view.rerender(<Harness root={root} calculationId={id} />),
  };
};

const row = (path: string) => document.getElementById(rowId(path))!;

async function expand(path: string) {
  fireEvent.click(row(path).querySelector("button.chevron")!);
  await waitFor(() =>
    expect(row(path).querySelector("button.chevron")).toHaveAttribute("aria-expanded", "true"),
  );
}

beforeEach(() => {
  calls.length = 0;
  handler = defaultHandler;
  localStorage.clear();
});

describe("colonnes", () => {
  it("le poids affiché est la chaîne servie, sans calcul", () => {
    // Valeurs incohérentes avec 12,3 % : un calcul local ne retomberait pas dessus.
    mount(
      line({
        share_of_total_pct: "12.3",
        unit_cost: { amount: "412.550000", currency: "EUR" },
        rolled_up_contribution: { amount: "825.100000", currency: "EUR" },
      }),
    );

    const cell = row("V").querySelector(".cell--share") as HTMLElement;
    expect(cell.textContent).toContain("12,3 %");
    expect((cell.querySelector("i") as HTMLElement).style.width).toBe("12.3%");
  });

  it("pas de poids sans calcul", () => {
    mount(line());

    const cell = row("V").querySelector(".cell--share") as HTMLElement;
    expect(cell.textContent).toBe("-");
    expect(cell.querySelector("i")).toBeNull();
  });

  it("la quantité sur ce chemin a sa colonne", () => {
    mount(line({ quantity_on_path: "15.000000" }));

    expect(row("V").querySelector(".cell--path-qty")!.textContent).toBe("15");
  });

  it("l'en-tête nomme les colonnes", () => {
    mount();

    const headers = screen.getAllByRole("columnheader");
    expect(headers.map((header) => header.textContent)).toEqual([
      "Pièce",
      "Réf.",
      "Qté / parent",
      "Qté / véhicule",
      "Coût unitaire",
      "Contribution",
      "Poids",
      "État",
    ]);
    expect(headers[5].getAttribute("title")).toContain("enfants compris, ne se somme pas");
  });
});

describe("états d'un nœud", () => {
  it("un nœud en cours de chargement le dit", async () => {
    handler = () => new Promise(() => {});
    mount();

    fireEvent.click(screen.getByLabelText("Déplier"));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("chargement…");
    expect(row("V").closest("li")!.contains(status)).toBe(true);
  });

  it("une erreur de dépliage se réessaie", async () => {
    let attempts = 0;
    handler = async (path, calculation) => {
      attempts += 1;
      if (attempts === 1) throw new Error("boom");
      return defaultHandler(path, calculation);
    };
    mount();

    fireEvent.click(screen.getByLabelText("Déplier"));
    await screen.findByText(/boom/);
    fireEvent.click(screen.getByRole("button", { name: "réessayer" }));

    await waitFor(() => expect(screen.getByText("Châssis")).toBeInTheDocument());
    expect(calls).toEqual(["V", "V"]);
  });

  it("un dépliage partiel le dit", async () => {
    handler = async () => page([child("V/A", "A"), child("V/B", "B")], 5);
    mount();

    await expand("V");

    expect(await screen.findByText("2 enfants sur 5")).toBeInTheDocument();
  });

  it("un nœud sans enfant servi le dit", async () => {
    handler = async () => page([], 0);
    mount();

    await expand("V");

    expect(await screen.findByText("aucun enfant")).toBeInTheDocument();
  });
});

describe("rafraîchissement", () => {
  it("signale la mise à jour sans changer les montants affichés", async () => {
    const old = child("V/A", "A", {
      rolled_up_contribution: { amount: "10.000000", currency: "EUR" },
    });
    handler = async () => page([old]);
    const view = mount(line(), "calc-1");
    await expand("V");
    await screen.findByText("Groupe motopropulseur");
    expect(screen.queryByText("mise à jour…")).toBeNull();

    handler = () => new Promise(() => {});
    view.withCalculation("calc-2");

    expect(await screen.findByText("mise à jour…")).toBeInTheDocument();
    expect(screen.getByText("10,00 €")).toBeInTheDocument();
  });
});

describe("tout replier", () => {
  it("cache les enfants et vide le dépliage mémorisé", async () => {
    handler = async (path) =>
      page(path === "V" ? [child("V/A", "A"), child("V/B", "B")] : path === "V/A" ? [child("V/A/M", "M")] : []);
    mount();
    await expand("V");
    await waitFor(() => expect(row("V/A")).not.toBeNull());
    await expand("V/A");
    await screen.findByText("Module");

    fireEvent.click(screen.getByRole("button", { name: "Tout replier" }));

    await waitFor(() => expect(screen.queryByText("Groupe motopropulseur")).toBeNull());
    expect(screen.queryByText("Module")).toBeNull();
    expect(localStorage.getItem(STORAGE_PREFIX + "bom-test")).toBe("[]");
    expect(within(document.body).getByText("Véhicule complet")).toBeInTheDocument();
  });
});
