/**
 * Les deux comportements de l'arbre qui peuvent être faux sans se voir :
 * le dépliage doit demander les enfants directs, et seulement eux ; et l'écran
 * ne doit additionner aucun montant.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Page,
  QuarantineEntry,
  Scenario,
  ScenarioParameter,
  TreeLine,
} from "../api/types";
import { Refusals } from "../quarantine";
import { useTreeState, type TreeState } from "../tree/useTreeState";
import { rowId, Tree } from "./Tree";

const calls: string[] = [];
// Réponses propres à un test ; vidée avant chaque test, pour que les autres
// reçoivent exactement les réponses par défaut.
const served = new Map<string, TreeLine[]>();

vi.mock("../api/client", () => ({
  ApiFailure: class extends Error {},
  api: {
    children: async (_version: string, path: string): Promise<Page<TreeLine>> => {
      calls.push(path);
      const items =
        served.get(path) ?? (path === "V" ? [child("V/A", "A"), child("V/B", "B")] : []);
      return {
        items,
        total: items.length,
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
  M: "Module de fixation",
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

let tree: TreeState;

function Harness({ root, scenario }: { root: TreeLine; scenario: Scenario | null }) {
  const state = useTreeState({ version: "bom-test", calculationId: null });
  tree = state;
  return (
    <Tree
      root={root}
      state={state}
      version="bom-test"
      scenario={scenario}
      onParameterChanged={() => {}}
      onShowWhereUsed={() => {}}
    />
  );
}

function mount(
  overrides: Partial<TreeLine> = {},
  refusals: ReadonlyMap<string, QuarantineEntry> = new Map(),
  scenario: Scenario | null = null,
) {
  return render(
    <Refusals.Provider value={refusals}>
      <Harness root={line(overrides)} scenario={scenario} />
    </Refusals.Provider>,
  );
}

function parameter(overrides: Partial<ScenarioParameter>): ScenarioParameter {
  return {
    parameter_id: "prm-1",
    part_ref: "A",
    scope: "part",
    path: null,
    supplier_id: null,
    plant_id: null,
    price_override: null,
    price_override_justification: null,
    ...overrides,
  };
}

function scenarioWith(parameters: ScenarioParameter[] = []): Scenario {
  return {
    id: "scn-1",
    name: "Scénario de test",
    bom_version: "bom-test",
    display_currency: "EUR",
    labour_rate: "42.00",
    active_rules: [],
    parameters,
    calculation_state: "NEVER_RUN",
    stale_reason: null,
    last_calculation_id: null,
  };
}

const row = (path: string) => document.getElementById(rowId(path));

async function expand(path: string) {
  (row(path)!.querySelector("button.chevron") as HTMLButtonElement).click();
  await waitFor(() => expect(row(path)!.querySelector("button.chevron")).toHaveAttribute("aria-expanded", "true"));
}

beforeEach(() => {
  calls.length = 0;
  served.clear();
  localStorage.clear();
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

describe("prix dégradés", () => {
  const refused: QuarantineEntry = {
    part_ref: "V",
    currency: "EUR",
    rejected_value: "-42.000000",
    reason: "prix négatif",
    replacement: { amount: "4.200000", currency: "EUR" },
    replacement_from_snapshot: "snp-hier",
    detected_at: "2026-09-24T08:33:42+00:00",
  };

  it("ne marque rien quand le prix est frais", () => {
    mount({ price_status: "OK" });

    expect(screen.queryByText(/prix de repli|prix en quarantaine/)).not.toBeInTheDocument();
  });

  it("dit qu'un prix vient d'un repli", () => {
    mount({ price_status: "FALLBACK" });

    expect(screen.getByText("prix de repli")).toBeInTheDocument();
    expect(screen.queryByText("prix en quarantaine")).not.toBeInTheDocument();
  });

  it("distingue une valeur refusée d'une valeur absente", () => {
    mount({ price_status: "QUARANTINED" });

    expect(screen.getByText("prix en quarantaine")).toBeInTheDocument();
    expect(screen.queryByText("prix de repli")).not.toBeInTheDocument();
  });

  it("dit sur la ligne ce qui a été refusé, pourquoi, et ce qui a été retenu", () => {
    mount({ price_status: "QUARANTINED" }, new Map([["V", refused]]));

    expect(screen.getByText("prix en quarantaine")).toHaveAttribute(
      "title",
      "« -42.000000 » refusé : prix négatif. Référence retenue : 4,20 € (snapshot snp-hier).",
    );
  });
});

describe("panneau de saisie", () => {
  it("déplier n'ouvre pas le panneau", async () => {
    const { container } = mount({}, new Map(), scenarioWith());

    (container.querySelector("button.chevron") as HTMLButtonElement).click();

    await waitFor(() =>
      expect(screen.getByText("Groupe motopropulseur")).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Ensemble fabriqué — V/)).toBeNull();
  });

  it("le panneau suit la ligne sélectionnée", async () => {
    const { container } = mount({}, new Map(), scenarioWith());
    await expand("V");
    await waitFor(() => expect(screen.getByText("Châssis")).toBeInTheDocument());

    // Le libellé d'un ensemble le déplie ; c'est « régler » qui ouvre le panneau.
    const settle = (path: string) =>
      (row(path)!.querySelector("button.row-action") as HTMLButtonElement).click();
    act(() => settle("V"));
    act(() => settle("V/B"));

    const panels = container.querySelectorAll(".panel");
    expect(panels).toHaveLength(1);
    expect(panels[0].textContent).toContain("Ensemble fabriqué — B");
    expect(row("V/B")).toHaveAttribute("aria-selected", "true");
    expect(row("V")).toHaveAttribute("aria-selected", "false");
  });
});

describe("marque de modification", () => {
  it("une ligne visée par un paramètre de portée pièce est marquée sans recalcul", async () => {
    mount({}, new Map(), scenarioWith([parameter({ scope: "part", part_ref: "A", path: null })]));
    await expand("V");
    await waitFor(() => expect(row("V/A")).not.toBeNull());

    expect(row("V/A")!.querySelector('[title="Paramètre modifié"]')).not.toBeNull();
    expect(row("V/B")!.querySelector('[title="Paramètre modifié"]')).toBeNull();
  });

  it("une portée chemin ne marque que son occurrence", async () => {
    served.set("V/A", [child("V/A/M", "M")]);
    served.set("V/B", [child("V/B/M", "M")]);
    mount(
      {},
      new Map(),
      scenarioWith([parameter({ scope: "path", part_ref: "M", path: "V/A/M" })]),
    );
    await expand("V");
    await waitFor(() => expect(row("V/B")).not.toBeNull());
    await expand("V/A");
    await expand("V/B");
    await waitFor(() => expect(row("V/B/M")).not.toBeNull());

    expect(row("V/A/M")!.querySelector('[title="Paramètre modifié"]')).not.toBeNull();
    expect(row("V/B/M")!.querySelector('[title="Paramètre modifié"]')).toBeNull();
  });
});

describe("suivi d'un chemin", () => {
  it("un ancêtre replié après reveal reste replié", async () => {
    served.set("V/A", [child("V/A/M", "M")]);
    mount();

    await act(() => tree.reveal("V/A/M"));
    await waitFor(() => expect(screen.getByText("Module de fixation")).toBeInTheDocument());

    act(() => (row("V/A")!.querySelector("button.chevron") as HTMLButtonElement).click());

    await waitFor(() =>
      expect(screen.queryByText("Module de fixation")).not.toBeInTheDocument(),
    );
    await expect(
      waitFor(() => expect(screen.getByText("Module de fixation")).toBeInTheDocument(), {
        timeout: 100,
      }),
    ).rejects.toThrow();
  });
});

it("chaque ligne a un id dérivé du chemin", async () => {
  mount();

  await expand("V");

  await waitFor(() => expect(document.getElementById("node-V/A")).not.toBeNull());
});

describe("clic sur le libellé", () => {
  it("déplie un ensemble, sans ouvrir son panneau", async () => {
    mount({}, new Map(), scenarioWith());

    act(() => screen.getByText("Véhicule complet").click());

    await waitFor(() => expect(screen.getByText("Groupe motopropulseur")).toBeInTheDocument());
    expect(row("V")).toHaveAttribute("aria-expanded", "true");
    expect(row("V")).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText(/Ensemble fabriqué — V/)).toBeNull();
  });

  it("replie un ensemble déplié", async () => {
    mount({}, new Map(), scenarioWith());
    await expand("V");

    act(() => screen.getByText("Véhicule complet").click());

    await waitFor(() => expect(row("V")).toHaveAttribute("aria-expanded", "false"));
    expect(screen.queryByText("Groupe motopropulseur")).toBeNull();
  });

  it("ouvre le panneau d'une feuille, qui n'a rien à déplier", async () => {
    mount(
      { has_children: false, child_count: 0, valuation_mode: "purchased" },
      new Map(),
      scenarioWith(),
    );

    act(() => screen.getByText("Véhicule complet").click());

    expect(await screen.findByText(/Pièce achetée — V/)).toBeInTheDocument();
  });

  it("le bouton « Régler » ouvre le panneau d'un ensemble, sans le déplier", async () => {
    mount({}, new Map(), scenarioWith());

    act(() => screen.getByRole("button", { name: "Régler cette pièce" }).click());

    expect(await screen.findByText(/Ensemble fabriqué — V/)).toBeInTheDocument();
    expect(row("V")).toHaveAttribute("aria-expanded", "false");
  });
});

describe("champs du panneau", () => {
  it("s'ouvrent vides, sans valeur d'exemple", async () => {
    mount({}, new Map(), scenarioWith());

    act(() => screen.getByRole("button", { name: "Régler cette pièce" }).click());

    const minutes = await screen.findByLabelText("Temps de main-d'œuvre (min)");
    expect(minutes).toHaveValue("");
    expect(minutes).not.toHaveAttribute("placeholder");
  });
});

describe("colonne référence", () => {
  it("une référence coupée à l'écran reste lisible en entier au survol", () => {
    mount({ part_ref: "CAR-BUMPER-FRONT-ASSY", label: "Pare-chocs avant" });

    expect(row("V")!.querySelector("code.ref")).toHaveAttribute("title", "CAR-BUMPER-FRONT-ASSY");
  });
});
