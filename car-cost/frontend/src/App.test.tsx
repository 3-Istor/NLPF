/**
 * L'écran entier, contre une API simulée : ce que l'utilisateur a déplié et
 * sélectionné doit survivre au recalcul, au réglage, au changement de
 * scénario et au rechargement de la page.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Calculation, Page, Scenario, TreeLine } from "./api/types";
import { App } from "./App";
import { api } from "./api/client";

const VERSION = import.meta.env.VITE_BOM_VERSION ?? "bom-multipla-2026-09-22";

// Le montant de « Vis de culasse » dépend du calcul demandé : c'est ce qui
// montre qu'une ligne affichée a bien été relue après un recalcul.
const SCREW_COST: Record<string, string> = {
  "calc-1": "11.00",
  "calc-2": "99.00",
  "calc-3": "33.00",
};

function line(overrides: Partial<TreeLine>): TreeLine {
  return {
    path: "V",
    part_ref: "VEH",
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

function lines(path: string, calculationId: string | null): TreeLine[] | null {
  if (path === "V") {
    return [
      line({ path: "V/A", part_ref: "GMP", label: "Groupe motopropulseur", child_count: 1 }),
      line({ path: "V/B", part_ref: "CHS", label: "Châssis", has_children: false, child_count: 0 }),
    ];
  }
  if (path === "V/A") {
    const cost = calculationId ? SCREW_COST[calculationId] : undefined;
    return [
      line({
        path: "V/A/X",
        part_ref: "VIS-12",
        label: "Vis de culasse",
        valuation_mode: "purchased",
        has_children: false,
        child_count: 0,
        rolled_up_contribution: cost ? { amount: cost, currency: "EUR" } : null,
      }),
    ];
  }
  if (path === "V/B" || path === "V/A/X") return [];
  return null;
}

function scenario(id: string, name: string, lastCalculationId: string): Scenario {
  return {
    id,
    name,
    bom_version: VERSION,
    display_currency: "EUR",
    labour_rate: "42.00",
    active_rules: [],
    parameters: [],
    calculation_state: "UP_TO_DATE",
    stale_reason: null,
    last_calculation_id: lastCalculationId,
  };
}

function calculation(id: string, scenarioId: string): Calculation {
  return {
    id,
    scenario_id: scenarioId,
    status: "OK",
    bom_version: VERSION,
    computed_at: "2026-10-01T08:00:00+00:00",
    input_digest: "sha256:0",
    display_currency: "EUR",
    total_cost: { amount: "5000.00", currency: "EUR" },
    price_snapshot: { id: "snp-1", age_seconds: 10, status: "FRESH" },
    systems: [],
    top_cost_contributors: [
      {
        part_ref: "VIS-12",
        label: "Contributeur vis de culasse",
        system: "MOT",
        cumulative_quantity: "16",
        own_contribution: { amount: "176.00", currency: "EUR" },
        share_pct: "3.52",
        first_path: "V/A/X",
      },
    ],
    parts_without_price: [],
    issue_counts: { missing_price: 0, quarantined: 0, fallback: 0 },
  };
}

// Du plus récent au plus ancien, comme l'API.
let stored: Scenario[] = [];

vi.mock("./api/client", () => ({
  ApiFailure: class extends Error {},
  api: {
    scenarios: vi.fn(async () => ({ items: stored, total: stored.length })),
    scenario: vi.fn(async (id: string) => {
      const found = stored.find((item) => item.id === id);
      if (!found) throw Object.assign(new Error("scénario inconnu"), { status: 404 });
      return found;
    }),
    calculation: vi.fn(async (id: string) => calculation(id, "scn-?")),
    quarantine: vi.fn(async (snapshotId: string) => ({ snapshot_id: snapshotId, items: [] })),
    root: vi.fn(async () => line({})),
    children: vi.fn(
      async (
        _version: string,
        path: string,
        calculationId: string | null,
      ): Promise<Page<TreeLine> & { path: string }> => {
        const items = lines(path, calculationId);
        if (!items) {
          throw Object.assign(new Error("chemin inconnu"), {
            code: "PATH_NOT_FOUND",
            status: 404,
          });
        }
        return { path, items, total: items.length, limit: 50, offset: 0 };
      },
    ),
    calculate: vi.fn(async (scenarioId: string) => {
      stored = stored.map((item) =>
        item.id === scenarioId ? { ...item, last_calculation_id: "calc-2" } : item,
      );
      return calculation("calc-2", scenarioId);
    }),
    putParameter: vi.fn(async () => ({
      parameter_id: "prm-1",
      scope: "part",
      part_ref: "GMP",
      affects_occurrences: 1,
      scope_label: "toutes les occurrences",
      calculation_state: "PARAMETERS_CHANGED",
      stale_reason: "parameters",
    })),
    part: vi.fn(async () => ({ suppliers: [] })),
    search: vi.fn(),
  },
}));

const children = vi.mocked(api.children);
const scrollIntoView = vi.fn();

beforeEach(() => {
  localStorage.clear();
  history.replaceState(null, "", "/");
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = scrollIntoView;
  stored = [
    scenario("scn-1", "Scénario récent", "calc-1"),
    scenario("scn-2", "Scénario ancien", "calc-3"),
  ];
});

const row = (path: string) => document.getElementById(`node-${path}`);

function chevron(path: string) {
  return within(row(path)!).getByRole("button", { name: /Déplier|Replier/ });
}

async function start() {
  render(<App />);
  await screen.findByText("Véhicule complet");
}

async function expandScrew() {
  fireEvent.click(chevron("V"));
  await screen.findByText("Groupe motopropulseur");
  fireEvent.click(chevron("V/A"));
  await screen.findByText("Vis de culasse");
}

const treeSection = () => document.querySelector("section.tree") as HTMLElement;

describe("l'écran garde l'arbre", () => {
  it("recalculer garde le dépliage et relit les chiffres du nouveau calcul", async () => {
    await start();
    await expandScrew();
    expect(screen.getByText("11,00 €")).toBeInTheDocument();
    const kept = document.getElementById("node-V/A");

    fireEvent.click(screen.getByRole("button", { name: "Recalculer" }));

    await screen.findByText("99,00 €");
    expect(screen.queryByText("11,00 €")).toBeNull();
    expect(children).toHaveBeenCalledWith(VERSION, "V", "calc-2");
    expect(children).toHaveBeenCalledWith(VERSION, "V/A", "calc-2");
    expect(kept?.isConnected).toBe(true);
  });

  it("appliquer un réglage ne replie rien", async () => {
    await start();
    await expandScrew();
    const kept = document.getElementById("node-V/A");

    fireEvent.click(screen.getByText("Groupe motopropulseur"));
    fireEvent.click(await screen.findByRole("button", { name: "Appliquer" }));

    await screen.findByText("toutes les occurrences");
    expect(api.putParameter).toHaveBeenCalled();
    expect(screen.getByText("Vis de culasse")).toBeInTheDocument();
    expect(kept?.isConnected).toBe(true);
  });

  it("la ligne sélectionnée est dans l'URL", async () => {
    await start();
    fireEvent.click(chevron("V"));
    fireEvent.click(await screen.findByText("Châssis"));

    await waitFor(() =>
      expect(new URLSearchParams(location.search).get("node")).toBe("V/B"),
    );
    expect(new URLSearchParams(location.search).get("scenario")).toBe("scn-1");
  });

  it("le F5 rouvre le scénario et la ligne de l'URL", async () => {
    history.replaceState(null, "", "/?scenario=scn-2&node=V/A");

    await start();

    expect(screen.getByLabelText("Scénario")).toHaveValue("scn-2");
    await waitFor(() =>
      expect(row("V/A")).toHaveAttribute("aria-selected", "true"),
    );
    await waitFor(() =>
      expect(scrollIntoView).toHaveBeenCalledWith({ block: "center" }),
    );
    const scrolled = scrollIntoView.mock.contexts.at(-1);
    expect(scrolled).toBe(row("V/A"));
  });

  it("un scénario inconnu dans l'URL retombe sur le plus récent", async () => {
    history.replaceState(null, "", "/?scenario=scn-inconnu");

    await start();

    expect(screen.getByLabelText("Scénario")).toHaveValue("scn-1");
    expect(document.querySelector(".banner--danger")).toBeNull();
    await waitFor(() =>
      expect(new URLSearchParams(location.search).get("scenario")).toBe("scn-1"),
    );
  });

  it("changer de scénario garde le dépliage", async () => {
    await start();
    await expandScrew();
    children.mockClear();

    fireEvent.change(screen.getByLabelText("Scénario"), {
      target: { value: "scn-2" },
    });

    await screen.findByText("33,00 €");
    expect(screen.getByText("Vis de culasse")).toBeInTheDocument();
    expect(children).toHaveBeenCalledWith(VERSION, "V", "calc-3");
    expect(children).toHaveBeenCalledWith(VERSION, "V/A", "calc-3");
  });

  it("aller à un contributeur déplie ses ancêtres, et on peut replier ensuite", async () => {
    await start();

    fireEvent.click(await screen.findByText("Contributeur vis de culasse"));

    await waitFor(() =>
      expect(row("V/A/X")).toHaveAttribute("aria-selected", "true"),
    );
    expect(chevron("V")).toHaveAttribute("aria-expanded", "true");
    expect(chevron("V/A")).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(chevron("V/A"));

    expect(within(treeSection()).queryByText("Vis de culasse")).toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(within(treeSection()).queryByText("Vis de culasse")).toBeNull();
  });

  it("aller à un résultat déplie ses ancêtres, sélectionne et fait défiler", async () => {
    vi.mocked(api.search).mockResolvedValue({
      items: [
        {
          part_ref: "VIS-12",
          label: "Vis de culasse",
          system: "MOT",
          occurrence_count: 1,
          paths: ["V/A/X"],
          paths_truncated: false,
        },
      ],
      total_parts: 1,
      total_occurrences: 1,
    });
    await start();

    const input = screen.getByRole("searchbox");
    fireEvent.change(input, { target: { value: "culasse" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(row("V/A/X")).toHaveAttribute("aria-selected", "true"),
    );
    expect(chevron("V")).toHaveAttribute("aria-expanded", "true");
    expect(chevron("V/A")).toHaveAttribute("aria-expanded", "true");
    await waitFor(() =>
      expect(scrollIntoView.mock.contexts).toContain(row("V/A/X")),
    );
    const call = scrollIntoView.mock.contexts.indexOf(row("V/A/X"));
    expect(scrollIntoView.mock.calls[call]).toEqual([{ block: "center" }]);
  });

  it("le terme cherché est surligné dans l'arbre, accents compris", async () => {
    vi.mocked(api.root).mockResolvedValueOnce(
      line({ path: "V", part_ref: "HARN-01", label: "Faisceau électrique", has_children: false }),
    );
    vi.mocked(api.search).mockResolvedValue({
      items: [
        {
          part_ref: "HARN-01",
          label: "Faisceau électrique",
          system: "ELE",
          occurrence_count: 1,
          paths: ["V"],
          paths_truncated: false,
        },
      ],
      total_parts: 1,
      total_occurrences: 1,
    });
    render(<App />);
    const input = await screen.findByRole("searchbox");
    await waitFor(() => expect(row("V")).not.toBeNull());

    fireEvent.change(input, { target: { value: "electrique" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(row("V")!.querySelector("mark")?.textContent).toBe("électrique"),
    );
  });
});
