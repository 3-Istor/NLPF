/**
 * L'écran entier, contre une API simulée : ce que l'utilisateur a déplié et
 * sélectionné doit survivre au recalcul, au réglage, au changement de
 * scénario et au rechargement de la page.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Calculation,
  CalculationSnapshot,
  Page,
  Scenario,
  TreeLine,
} from "./api/types";
import { App } from "./App";
import { api, ApiFailure } from "./api/client";

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
    total_co2: { kg_co2e: "980.000000" },
    top_co2_contributors: [],
    parts_without_price: [],
    parts_without_co2: [],
    issue_counts: { missing_price: 0, quarantined: 0, fallback: 0 },
  };
}

// Du plus récent au plus ancien, comme l'API.
let stored: Scenario[] = [];
let storedSnapshots: ReturnType<typeof frozen>[] = [];

function frozen(id: string, name: string, scenarioId: string, calculationId: string) {
  return {
    id,
    name,
    bom_version: VERSION,
    scenario_id: scenarioId,
    scenario_name: "Scénario figé",
    calculation_id: calculationId,
    price_snapshot_id: "snp-1",
    created_at: "2026-10-01T09:00:00+00:00",
    display_currency: "EUR",
    labour_rate: "42.00",
    active_rules: [] as string[],
    parameters: [] as CalculationSnapshot["parameters"],
    name_history: [{ name, renamed_at: "2026-10-01T09:00:00+00:00" }],
  };
}

vi.mock("./api/client", () => ({
  ApiFailure: class extends Error {
    constructor(
      readonly code: string,
      message: string,
      readonly status: number,
    ) {
      super(message);
    }
  },
  api: {
    bomVersions: vi.fn(async () => ({
      items: [
        {
          id: "bom-valhalla-hybride-2026-10-02",
          label: "Aston Martin Valhalla — hybride rechargeable (PHEV)",
          root_part_ref: "VEH-VALHALLA-HYB",
          part_count: 659,
          edge_count: 658,
          validated_at: "2026-10-02T08:00:00+00:00",
          is_synthetic: true,
          reference_labour_rate: "60.00",
        },
        {
          id: VERSION,
          label: "Fiat Multipla 1.6 16V",
          root_part_ref: "VEH",
          part_count: 474,
          edge_count: 689,
          validated_at: "2026-09-22T08:00:00+00:00",
          is_synthetic: true,
          reference_labour_rate: "42.00",
        },
      ],
    })),
    createScenario: vi.fn(async (body: { bom_version: string; name: string; labour_rate: string }) => {
      const created = {
        ...scenario("scn-neuf", body.name, "calc-1"),
        bom_version: body.bom_version,
        labour_rate: body.labour_rate,
        last_calculation_id: null,
        calculation_state: "NEVER_RUN" as const,
      };
      stored = [created, ...stored];
      return created;
    }),
    scenarios: vi.fn(async () => ({ items: stored, total: stored.length })),
    scenario: vi.fn(async (id: string) => {
      const found = stored.find((item) => item.id === id);
      if (!found) throw Object.assign(new Error("scénario inconnu"), { status: 404 });
      return found;
    }),
    calculation: vi.fn(async (id: string) => calculation(id, "scn-?")),
    calculateLive: vi.fn(async (scenarioId: string) => ({
      ...calculation("live-1", scenarioId),
      price_mode: "LIVE" as const,
      prices_taken_at: "2026-10-02T09:00:00+00:00",
    })),
    takePriceSnapshot: vi.fn(async () => ({ id: "snp-figé" })),
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
    freezeCalculation: vi.fn(async (scenarioId: string, name: string) => ({
      ...frozen("csn-9", name, scenarioId, "calc-9"),
    })),
    calculationSnapshots: vi.fn(async () => ({
      items: storedSnapshots,
      total: storedSnapshots.length,
    })),
    calculationSnapshot: vi.fn(async (id: string) => {
      const found = storedSnapshots.find((item) => item.id === id);
      if (!found) throw new Error("snapshot de calcul inconnu");
      return found;
    }),
    part: vi.fn(async () => ({ suppliers: [] })),
    search: vi.fn(),
    deriveScenario: vi.fn(async (snapshotId: string, name: string) => {
      const created = {
        ...scenario("scn-repris", name, "calc-1"),
        calculation_state: "NEVER_RUN" as const,
        last_calculation_id: null,
        derived_from: snapshotId,
      };
      stored = [created, ...stored];
      return created;
    }),
    deleteScenario: vi.fn(),
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
  storedSnapshots = [];
});

const row = (path: string) => document.getElementById(`node-${path}`);

/**
 * Ouvre le panneau d'une ligne. Le libellé d'un ensemble le déplie ; c'est le
 * bouton « régler » (ou « réglages », pour un snapshot ouvert) qui ouvre le panneau.
 */
function openSettings(path: string) {
  fireEvent.click(
    within(row(path)!).getByRole("button", { name: /Régler cette pièce|Voir les réglages figés/ }),
  );
}

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

    openSettings("V/A");
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

describe("les snapshots de calcul", () => {
  const freezeAs = async (name: string) => {
    fireEvent.click(screen.getByRole("button", { name: "Figer sous un nom" }));
    fireEvent.change(screen.getByLabelText("Nom du snapshot de calcul"), {
      target: { value: name },
    });
    fireEvent.click(screen.getByRole("button", { name: "Figer" }));
  };

  it("figer affiche le nom dans l'en-tête et dans la liste", async () => {
    await start();
    await expandScrew();
    vi.mocked(api.freezeCalculation).mockImplementationOnce(async (id, name) => {
      const created = frozen("csn-9", name, id, "calc-9");
      storedSnapshots = [created];
      return created;
    });

    await freezeAs("Référence T3");

    await screen.findByText("Snapshot de calcul :", { exact: false });
    expect(api.freezeCalculation).toHaveBeenCalledWith("scn-1", "Référence T3");
    expect(document.querySelector(".snapshot-title")).toHaveTextContent(
      "Snapshot de calcul : Référence T3",
    );
    expect(
      within(screen.getByLabelText("Snapshots de calcul")).getByText("Référence T3"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(children).toHaveBeenCalledWith(VERSION, "V", "calc-9", "csn-9");
      expect(children).toHaveBeenCalledWith(VERSION, "V/A", "calc-9", "csn-9");
    });
  });

  it("ouvrir un snapshot affiche son calcul figé et son nom", async () => {
    storedSnapshots = [
      frozen("csn-1", "Référence T3", "scn-1", "calc-1"),
      frozen("csn-2", "Variante Turquie", "scn-2", "calc-2"),
    ];
    await start();
    await expandScrew();

    fireEvent.change(screen.getByLabelText("Snapshots de calcul"), {
      target: { value: "csn-2" },
    });

    await waitFor(() =>
      expect(document.querySelector(".snapshot-title")).toHaveTextContent(
        "Snapshot de calcul : Variante Turquie",
      ),
    );
    expect(api.calculation).toHaveBeenCalledWith("calc-2");
    expect(screen.getByLabelText("Scénario")).toHaveValue("scn-2");
    await screen.findByText("99,00 €");
    expect(screen.getByText("Vis de culasse")).toBeInTheDocument();
  });

  it("recalculer revient au scénario vivant", async () => {
    storedSnapshots = [frozen("csn-2", "Variante Turquie", "scn-2", "calc-2")];
    await start();
    fireEvent.change(screen.getByLabelText("Snapshots de calcul"), {
      target: { value: "csn-2" },
    });
    await screen.findByText("Snapshot de calcul :", { exact: false });

    fireEvent.click(screen.getByRole("button", { name: "Recalculer" }));

    await waitFor(() =>
      expect(screen.queryByText("Snapshot de calcul :", { exact: false })).toBeNull(),
    );
  });

  it("un nom déjà pris est expliqué", async () => {
    await start();
    vi.mocked(api.freezeCalculation).mockRejectedValueOnce(
      new ApiFailure(
        "SNAPSHOT_NAME_TAKEN",
        "le nom « Référence T3 » est déjà pris dans cette version",
        409,
      ),
    );

    await freezeAs("Référence T3");

    await screen.findByText(/est déjà pris dans cette version/);
    expect(screen.queryByText("Snapshot de calcul :", { exact: false })).toBeNull();
  });
});

describe("un snapshot ouvert est en lecture seule", () => {
  const onEngine = {
    part_ref: "GMP",
    scope: "part" as const,
    path: null,
    supplier_id: null,
    plant_id: null,
    price_override: null,
    price_override_justification: null,
    labour_minutes: "12.5",
    purchase_currency: null,
  };

  async function openSnapshot(id: string) {
    fireEvent.change(screen.getByLabelText("Snapshots de calcul"), {
      target: { value: id },
    });
    await screen.findByText("Snapshot de calcul :", { exact: false });
  }

  beforeEach(() => {
    storedSnapshots = [
      { ...frozen("csn-2", "Variante Turquie", "scn-2", "calc-2"), parameters: [onEngine] },
    ];
  });

  it("n'offre aucun panneau de saisie, mais les réglages copiés de la ligne", async () => {
    await start();
    await expandScrew();
    await openSnapshot("csn-2");

    openSettings("V/A");

    const copied = await screen.findByRole("region", { name: "Réglages figés — GMP" });
    expect(within(copied).getByText("toutes les occurrences")).toBeInTheDocument();
    expect(within(copied).getByText("12.5 min")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Appliquer" })).toBeNull();
    // Aucun choix de portée : la synthèse, elle, garde son choix Coût / CO₂.
    expect(screen.queryByRole("group", { name: "Portée du réglage" })).toBeNull();
    expect(screen.queryByRole("radio", { name: /occurrence/ })).toBeNull();
  });

  it("dit qu'une ligne n'a aucun réglage dans le snapshot", async () => {
    await start();
    await expandScrew();
    await openSnapshot("csn-2");

    fireEvent.click(screen.getByText("Châssis"));

    const copied = await screen.findByRole("region", { name: "Réglages figés — CHS" });
    expect(within(copied).getByText(/Aucun réglage/)).toBeInTheDocument();
  });

  it("la synthèse dit « figé », ni « à jour » ni « obsolète »", async () => {
    stored = [
      stored[0],
      { ...scenario("scn-2", "Scénario ancien", "calc-3"), calculation_state: "PARAMETERS_CHANGED", stale_reason: "parameters" },
    ];
    await start();
    await openSnapshot("csn-2");

    const summary = document.querySelector("aside.summary") as HTMLElement;
    expect(within(summary).getByText("figé")).toBeInTheDocument();
    expect(within(summary).queryByText("à jour")).toBeNull();
    expect(within(summary).queryByText("totaux obsolètes")).toBeNull();
    expect(within(summary).queryByText(/ne sont plus à jour/)).toBeNull();
  });

  it("les marques viennent de la copie, servie par le serveur, pas du scénario vivant", async () => {
    stored = [
      stored[0],
      {
        ...scenario("scn-2", "Scénario ancien", "calc-3"),
        parameters: [{ ...onEngine, part_ref: "CHS", parameter_id: "prm-9" }],
      },
    ];
    await start();
    fireEvent.click(chevron("V"));
    await screen.findByText("Châssis");
    await openSnapshot("csn-2");

    expect(api.root).toHaveBeenLastCalledWith(VERSION, "calc-2", "csn-2");
    await waitFor(() =>
      expect(children).toHaveBeenCalledWith(VERSION, "V", "calc-2", "csn-2"),
    );
    expect(row("V/B")).not.toHaveClass("row--modified");
  });

  it("« Revenir au scénario » rend le scénario vivant éditable", async () => {
    await start();
    await expandScrew();
    await openSnapshot("csn-2");

    fireEvent.click(screen.getByRole("button", { name: "Revenir au scénario" }));

    await waitFor(() =>
      expect(screen.queryByText("Snapshot de calcul :", { exact: false })).toBeNull(),
    );
    openSettings("V/A");
    expect(await screen.findByRole("button", { name: "Appliquer" })).toBeInTheDocument();
    expect(api.root).toHaveBeenLastCalledWith(VERSION, "calc-3");
  });
});

describe("repartir d'un snapshot de calcul", () => {
  beforeEach(() => {
    storedSnapshots = [frozen("csn-2", "Variante Turquie", "scn-2", "calc-2")];
  });

  async function openSnapshot() {
    fireEvent.change(screen.getByLabelText("Snapshots de calcul"), {
      target: { value: "csn-2" },
    });
    await screen.findByText("Snapshot de calcul :", { exact: false });
  }

  it("le bouton n'existe que sur un snapshot ouvert", async () => {
    await start();
    expect(screen.queryByRole("button", { name: "Repartir de ce snapshot" })).toBeNull();

    await openSnapshot();

    expect(
      screen.getByRole("button", { name: "Repartir de ce snapshot" }),
    ).toBeInTheDocument();
  });

  it("crée un scénario au nom proposé, modifiable, et l'ouvre éditable", async () => {
    await start();
    await expandScrew();
    await openSnapshot();

    fireEvent.click(screen.getByRole("button", { name: "Repartir de ce snapshot" }));
    const field = screen.getByLabelText("Nom du scénario repris");
    expect(field).toHaveValue("");
    fireEvent.change(field, { target: { value: "Variante Turquie — reprise d'octobre" } });
    fireEvent.click(screen.getByRole("button", { name: "Créer le scénario" }));

    await waitFor(() =>
      expect(screen.queryByText("Snapshot de calcul :", { exact: false })).toBeNull(),
    );
    expect(api.deriveScenario).toHaveBeenCalledWith(
      "csn-2",
      "Variante Turquie — reprise d'octobre",
    );
    expect(screen.getByLabelText("Scénario")).toHaveValue("scn-repris");
    openSettings("V/A");
    expect(await screen.findByRole("button", { name: "Appliquer" })).toBeInTheDocument();
  });

  it("un réglage qui ne s'applique plus est refusé en nommant les pièces", async () => {
    await start();
    await openSnapshot();
    vi.mocked(api.deriveScenario).mockRejectedValueOnce(
      new ApiFailure(
        "SNAPSHOT_SETTINGS_NOT_APPLICABLE",
        "réglages du snapshot inapplicables : VIS-12 (fournisseur indisponible); V/A/X (usine refusée)",
        422,
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Repartir de ce snapshot" }));
    fireEvent.change(screen.getByLabelText("Nom du scénario repris"), {
      target: { value: "Reprise d'octobre" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Créer le scénario" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("VIS-12");
    expect(alert).toHaveTextContent("V/A/X");
    expect(screen.getByText("Snapshot de calcul :", { exact: false })).toBeInTheDocument();
    expect(screen.getByLabelText("Scénario")).toHaveValue("scn-2");
  });
});

describe("des messages d'erreur fiables", () => {
  it("une liste de snapshots illisible est une erreur, pas une liste vide", async () => {
    vi.mocked(api.calculationSnapshots).mockRejectedValueOnce(
      new ApiFailure("UNKNOWN", "relation calculation_snapshot inexistante", 500),
    );

    await start();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("relation calculation_snapshot inexistante");
    expect(screen.queryByText("Aucun snapshot de calcul")).toBeNull();
  });

  it("un gel réussi ferme le champ même si la liste ne se relit pas", async () => {
    await start();
    vi.mocked(api.calculationSnapshots).mockRejectedValueOnce(
      new ApiFailure("UNKNOWN", "réseau coupé", 503),
    );

    fireEvent.click(screen.getByRole("button", { name: "Figer sous un nom" }));
    fireEvent.change(screen.getByLabelText("Nom du snapshot de calcul"), {
      target: { value: "Référence T3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Figer" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("« Référence T3 » figé");
    expect(alert).toHaveTextContent("réseau coupé");
    expect(screen.queryByLabelText("Nom du snapshot de calcul")).toBeNull();
    expect(document.querySelector(".snapshot-title")).toHaveTextContent(
      "Snapshot de calcul : Référence T3",
    );
  });

  it("supprimer efface l'erreur précédente avant d'appeler le serveur", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await start();
    vi.mocked(api.freezeCalculation).mockRejectedValueOnce(
      new ApiFailure("SNAPSHOT_NAME_TAKEN", "nom déjà pris", 409),
    );
    fireEvent.click(screen.getByRole("button", { name: "Figer sous un nom" }));
    fireEvent.change(screen.getByLabelText("Nom du snapshot de calcul"), {
      target: { value: "Référence T3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Figer" }));
    await screen.findByText(/nom déjà pris/);
    vi.mocked(api.deleteScenario).mockReturnValueOnce(new Promise(() => {}));

    fireEvent.click(screen.getByRole("button", { name: "Supprimer" }));

    await waitFor(() => expect(screen.queryByText(/nom déjà pris/)).toBeNull());
    expect(api.deleteScenario).toHaveBeenCalledWith("scn-1");
  });
});

describe("supprimer un scénario porteur de snapshots", () => {
  it("le refus 409 nomme les snapshots qui le retiennent", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(api.deleteScenario).mockRejectedValueOnce(
      new ApiFailure(
        "SCENARIO_HAS_SNAPSHOTS",
        "le scénario porte des snapshots de calcul : Référence T3, Variante Turquie",
        409,
      ),
    );
    await start();

    fireEvent.click(screen.getByRole("button", { name: "Supprimer" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("SCENARIO_HAS_SNAPSHOTS");
    expect(alert).toHaveTextContent("Référence T3, Variante Turquie");
    expect(screen.getByLabelText("Scénario")).toHaveValue("scn-1");
  });
});

describe("données synthétiques", () => {
  it("l'en-tête ne répète plus l'avertissement, la synthèse le porte à côté des chiffres", async () => {
    await start();

    expect(screen.queryByText(/aucune\s+donnée constructeur/)).toBeNull();
    expect(await screen.findByText("plausibles mais synthétiques")).toBeInTheDocument();
  });
});

describe("choix de la nomenclature", () => {
  it("ouvre le Multipla par défaut, avant les Valhalla", async () => {
    render(<App />);
    const select = await screen.findByLabelText("Nomenclature ouverte");
    expect((select as HTMLSelectElement).value).toBe(VERSION);
  });

  it("changer de véhicule rouvre l'espace sur sa nomenclature, avec son taux", async () => {
    render(<App />);
    const select = await screen.findByLabelText("Nomenclature ouverte");
    await waitFor(() => expect(api.root).toHaveBeenCalledWith(VERSION, "calc-1"));

    fireEvent.change(select, { target: { value: "bom-valhalla-hybride-2026-10-02" } });

    // Aucun scénario n'existe pour la Valhalla : un scénario de travail est
    // créé au taux de sa nomenclature, pas à celui du Multipla.
    await waitFor(() =>
      expect(api.createScenario).toHaveBeenCalledWith(
        expect.objectContaining({
          bom_version: "bom-valhalla-hybride-2026-10-02",
          labour_rate: "60.00",
        }),
      ),
    );
    expect(new URLSearchParams(window.location.search).get("bom")).toBe(
      "bom-valhalla-hybride-2026-10-02",
    );
  });
});

describe("prix en direct ou figés", () => {
  it("en direct, le calcul vient de l'API et la synthèse dit qu'il n'est pas enregistré", async () => {
    render(<App />);
    fireEvent.click(await screen.findByLabelText("En direct"));
    await waitFor(() => expect(api.calculateLive).toHaveBeenCalledWith("scn-1"));
    expect(await screen.findByText("prix en direct")).toBeInTheDocument();
    expect(screen.getByText(/ce total\s+n'est pas enregistré/)).toBeInTheDocument();
    await waitFor(() => expect(api.root).toHaveBeenCalledWith(VERSION, "live-1"));
  });

  it("figer les prix prend un snapshot puis calcule dessus", async () => {
    render(<App />);
    fireEvent.click(await screen.findByLabelText("En direct"));
    await waitFor(() => expect(api.calculateLive).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Figer les prix maintenant" }));

    await waitFor(() => expect(api.takePriceSnapshot).toHaveBeenCalledWith(VERSION, "EUR"));
    await waitFor(() => expect(api.calculate).toHaveBeenCalledWith("scn-1"));
    expect((screen.getByLabelText("Snapshot") as HTMLInputElement).checked).toBe(true);
  });
});
