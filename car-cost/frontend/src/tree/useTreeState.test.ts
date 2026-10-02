/**
 * L'état de l'arbre : ce qui est déplié survit au recalcul et au rechargement.
 *
 * L'identité d'une ligne est son chemin. La fixture monte une sous-assemblée
 * partagée `M` sous `A` et sous `B` : deux occurrences, deux chemins, deux
 * états de dépliage indépendants.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { TreeLine } from "../api/types";
import { useTreeState } from "./useTreeState";

vi.mock("../api/client", () => ({ api: { children: vi.fn() } }));

const children = vi.mocked(api.children);

const LABELS: Record<string, string> = {
  V: "Véhicule",
  A: "Groupe motopropulseur",
  B: "Châssis",
  M: "Module de fixation",
  X: "Vis de fixation",
};

const TREE: Record<string, string[]> = {
  V: ["A", "B"],
  "V/A": ["M"],
  "V/B": ["M"],
  "V/A/M": ["X"],
  "V/B/M": ["X"],
  "V/A/M/X": [],
};

// Un montant différent par calcul : on reconnaît d'où vient une page servie.
const AMOUNT: Record<string, string> = {
  none: "0.00",
  "calc-1": "111.00",
  "calc-2": "222.00",
  "calc-3": "333.00",
};

function line(path: string, calculationId: string | null): TreeLine {
  const ref = path.split("/").at(-1)!;
  return {
    path,
    part_ref: ref,
    label: LABELS[ref],
    system: "Structure",
    valuation_mode: "manufactured",
    unit: "pc",
    edge_quantity: "1",
    has_children: (TREE[path] ?? []).length > 0,
    child_count: (TREE[path] ?? []).length,
    parent_count: ref === "M" ? 2 : 1,
    occurrence_count: ref === "M" || ref === "X" ? 2 : 1,
    rolled_up_contribution: {
      amount: AMOUNT[calculationId ?? "none"],
      currency: "EUR",
    },
  };
}

function page(path: string, calculationId: string | null) {
  const items = (TREE[path] ?? []).map((ref) => line(`${path}/${ref}`, calculationId));
  return { path, items, total: items.length, limit: 100, offset: 0 };
}

type Pending = {
  path: string;
  calculationId: string | null;
  resolve: () => void;
  reject: (error: unknown) => void;
};

let pending: Pending[] = [];
let inFlight = 0;
let maxInFlight = 0;

/** Chaque appel attend qu'on le résolve à la main. */
function deferResponses() {
  children.mockImplementation(
    (_version, path, calculationId) =>
      new Promise((resolve, reject) => {
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        const settle = () => {
          inFlight -= 1;
          pending = pending.filter((entry) => entry !== item);
        };
        const item: Pending = {
          path,
          calculationId,
          resolve: () => {
            settle();
            resolve(page(path, calculationId));
          },
          reject: (error) => {
            settle();
            reject(error);
          },
        };
        pending.push(item);
      }),
  );
}

/** Chaque appel répond aussitôt la page du calcul demandé. */
function answerAtOnce() {
  children.mockImplementation(async (_version, path, calculationId) =>
    page(path, calculationId),
  );
}

function calledPaths(calculationId?: string | null) {
  return children.mock.calls
    .filter(([, , calc]) => calculationId === undefined || calc === calculationId)
    .map(([, path]) => path);
}

function mount(calculationId: string | null = null) {
  return renderHook(
    (props: { calculationId: string | null }) =>
      useTreeState({ version: "bom-test", calculationId: props.calculationId }),
    { initialProps: { calculationId } },
  );
}

async function resolveAll(filter: (entry: Pending) => boolean = () => true) {
  await act(async () => {
    for (const entry of pending.filter(filter)) entry.resolve();
  });
}

function amountsOf(result: { current: ReturnType<typeof useTreeState> }, path: string) {
  const entry = result.current.childrenOf(path);
  if (entry?.status !== "ready") return entry?.status;
  return entry.page.items.map((item) => item.rolled_up_contribution?.amount);
}

beforeEach(() => {
  localStorage.clear();
  children.mockReset();
  pending = [];
  inFlight = 0;
  maxInFlight = 0;
});

afterEach(() => vi.restoreAllMocks());

describe("useTreeState", () => {
  it("déplier charge les enfants directs une fois", async () => {
    answerAtOnce();
    const { result } = mount();

    await act(async () => result.current.toggle("V"));

    expect(result.current.isExpanded("V")).toBe(true);
    expect(children.mock.calls).toEqual([["bom-test", "V", null]]);
    expect(result.current.childrenOf("V")?.status).toBe("ready");

    await act(async () => result.current.toggle("V"));
    expect(result.current.isExpanded("V")).toBe(false);
    await act(async () => result.current.toggle("V"));

    expect(result.current.isExpanded("V")).toBe(true);
    expect(children).toHaveBeenCalledTimes(1);
  });

  it("déplier une occurrence d'une pièce partagée n'ouvre pas l'autre", async () => {
    answerAtOnce();
    const { result } = mount();

    await act(async () => result.current.toggle("V/A/M"));

    expect(result.current.isExpanded("V/A/M")).toBe(true);
    expect(result.current.isExpanded("V/B/M")).toBe(false);
    expect(calledPaths()).toEqual(["V/A/M"]);
    expect(result.current.childrenOf("V/B/M")).toBeUndefined();
  });

  it("un recalcul redemande chaque chemin déplié avec le nouveau calcul", async () => {
    answerAtOnce();
    const { result, rerender } = mount("calc-1");
    await act(async () => result.current.toggle("V"));
    await act(async () => result.current.toggle("V/A"));
    expect(amountsOf(result, "V")).toEqual(["111.00", "111.00"]);

    rerender({ calculationId: "calc-2" });

    await waitFor(() => {
      expect(result.current.childrenOf("V")).toMatchObject({
        status: "ready",
        calculationId: "calc-2",
      });
      expect(result.current.childrenOf("V/A")).toMatchObject({
        status: "ready",
        calculationId: "calc-2",
      });
    });
    expect(children).toHaveBeenCalledWith("bom-test", "V", "calc-2");
    expect(children).toHaveBeenCalledWith("bom-test", "V/A", "calc-2");
    expect([...result.current.expanded].sort()).toEqual(["V", "V/A"]);
    expect(amountsOf(result, "V")).toEqual(["222.00", "222.00"]);
    expect(amountsOf(result, "V/A")).toEqual(["222.00"]);
  });

  it("jamais plus de 4 requêtes simultanées", async () => {
    const six = ["V", "V/A", "V/B", "V/A/M", "V/B/M", "V/A/M/X"];
    localStorage.setItem("3istor.tree.bom-test", JSON.stringify(six));
    answerAtOnce();
    const { result, rerender } = mount("calc-1");
    await waitFor(() => expect(children).toHaveBeenCalledTimes(6));

    deferResponses();
    rerender({ calculationId: "calc-2" });

    // On sert au compte-gouttes : chaque réponse libère une place.
    for (let round = 0; round < 6; round++) {
      await waitFor(() => expect(pending.length).toBeGreaterThan(0));
      await act(async () => pending[0].resolve());
    }
    expect(pending).toHaveLength(0);

    expect(maxInFlight).toBe(4);
    expect(calledPaths("calc-2").sort()).toEqual([...six].sort());
    for (const path of six) {
      expect(result.current.childrenOf(path)).toMatchObject({
        status: "ready",
        calculationId: "calc-2",
      });
    }
  });

  it("une réponse périmée n'écrase pas la récente", async () => {
    answerAtOnce();
    const { result, rerender } = mount("calc-1");
    await act(async () => result.current.toggle("V"));
    await act(async () => result.current.toggle("V/A"));

    deferResponses();
    rerender({ calculationId: "calc-2" });
    await waitFor(() => expect(pending.length).toBe(2));
    rerender({ calculationId: "calc-3" });
    await waitFor(() => expect(pending.length).toBe(4));

    await resolveAll((entry) => entry.calculationId === "calc-3");
    await resolveAll((entry) => entry.calculationId === "calc-2");

    expect(result.current.childrenOf("V")).toMatchObject({
      status: "ready",
      calculationId: "calc-3",
    });
    expect(result.current.childrenOf("V/A")).toMatchObject({
      status: "ready",
      calculationId: "calc-3",
    });
    expect(amountsOf(result, "V")).toEqual(["333.00", "333.00"]);
    expect(amountsOf(result, "V/A")).toEqual(["333.00"]);
  });

  it("un chemin disparu est élagué sans erreur", async () => {
    localStorage.setItem(
      "3istor.tree.bom-test",
      JSON.stringify(["V", "V/B", "V/B/M"]),
    );
    answerAtOnce();
    const { result, rerender } = mount("calc-1");
    await waitFor(() => expect(children).toHaveBeenCalledTimes(3));

    children.mockImplementation(async (_version, path, calculationId) => {
      if (path === "V/B") throw { code: "PATH_NOT_FOUND", status: 404 };
      return page(path, calculationId);
    });
    rerender({ calculationId: "calc-2" });

    await waitFor(() => expect(result.current.isExpanded("V/B")).toBe(false));
    expect(result.current.isExpanded("V/B/M")).toBe(false);
    expect(result.current.isExpanded("V")).toBe(true);
    expect(result.current.childrenOf("V/B")?.status).not.toBe("error");
    await waitFor(() =>
      expect(result.current.childrenOf("V")).toMatchObject({ calculationId: "calc-2" }),
    );
  });

  it("une autre erreur reste visible et se réessaie", async () => {
    children.mockRejectedValue(new Error("boom"));
    const { result } = mount();

    await act(async () => result.current.toggle("V"));

    expect(result.current.childrenOf("V")).toEqual({ status: "error", message: "boom" });
    expect(result.current.isExpanded("V")).toBe(true);

    answerAtOnce();
    await act(async () => result.current.retry("V"));

    expect(children).toHaveBeenCalledTimes(2);
    expect(result.current.childrenOf("V")?.status).toBe("ready");
  });

  it("le dépliage survit au rechargement", async () => {
    answerAtOnce();
    const first = mount();
    await act(async () => first.result.current.toggle("V"));

    expect(JSON.parse(localStorage.getItem("3istor.tree.bom-test")!)).toContain("V");
    first.unmount();

    localStorage.setItem("3istor.tree.bom-test", JSON.stringify(["V", "V/A"]));
    children.mockClear();
    const { result } = mount();

    expect([...result.current.expanded].sort()).toEqual(["V", "V/A"]);
    await waitFor(() => expect(children).toHaveBeenCalledTimes(2));
    expect(calledPaths().sort()).toEqual(["V", "V/A"]);
  });

  it("un stockage qui lève une exception n'empêche rien", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("stockage refusé");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("stockage refusé");
    });
    answerAtOnce();
    const { result } = mount();

    await act(async () => result.current.toggle("V"));

    expect(result.current.isExpanded("V")).toBe(true);
    expect(result.current.childrenOf("V")?.status).toBe("ready");
  });

  it("tout replier", async () => {
    answerAtOnce();
    const { result } = mount();
    await act(async () => result.current.toggle("V"));
    await act(async () => result.current.toggle("V/A"));

    act(() => result.current.collapseAll());

    expect(result.current.expanded.size).toBe(0);
    expect(JSON.parse(localStorage.getItem("3istor.tree.bom-test")!)).toEqual([]);
  });

  it("reveal déplie les ancêtres et sélectionne", async () => {
    answerAtOnce();
    const { result } = mount();

    await act(async () => result.current.reveal("V/A/M/X"));

    expect(calledPaths()).toEqual(["V", "V/A", "V/A/M"]);
    expect(result.current.isExpanded("V")).toBe(true);
    expect(result.current.isExpanded("V/A")).toBe(true);
    expect(result.current.isExpanded("V/A/M")).toBe(true);
    expect(result.current.isExpanded("V/A/M/X")).toBe(false);
    expect(result.current.selected).toBe("V/A/M/X");
  });

  it("un ancêtre replié après reveal reste replié", async () => {
    answerAtOnce();
    const { result, rerender } = mount();
    await act(async () => result.current.reveal("V/A/M/X"));

    act(() => result.current.toggle("V/A"));
    rerender({ calculationId: null });
    await act(async () => {});

    expect(result.current.isExpanded("V/A")).toBe(false);
    expect(calledPaths().filter((path) => path === "V/A")).toHaveLength(1);
  });

  describe("sous-niveaux cachés par le repli d'un parent", () => {
    function stored() {
      return JSON.parse(localStorage.getItem("3istor.tree.bom-test")!);
    }

    it("replier un parent cache ses sous-niveaux sans les oublier", async () => {
      answerAtOnce();
      const { result } = mount();
      await act(async () => result.current.toggle("V"));
      await act(async () => result.current.toggle("V/A"));

      act(() => result.current.toggle("V"));

      expect(result.current.isExpanded("V")).toBe(false);
      expect(stored()).toContain("V/A");
      expect(stored()).not.toContain("V");

      await act(async () => result.current.toggle("V"));

      expect(result.current.isExpanded("V")).toBe(true);
      expect(result.current.isExpanded("V/A")).toBe(true);
      // Même calcul : les pages sont déjà là, rien n'est redemandé.
      expect(calledPaths()).toEqual(["V", "V/A"]);
    });

    it("un recalcul ne redemande que les pages visibles, la réouverture recharge le reste", async () => {
      answerAtOnce();
      const { result, rerender } = mount("calc-1");
      await act(async () => result.current.toggle("V"));
      await act(async () => result.current.toggle("V/A"));
      await act(async () => result.current.toggle("V/A/M"));
      await act(async () => result.current.toggle("V/B"));
      act(() => result.current.toggle("V/A"));

      rerender({ calculationId: "calc-2" });
      await waitFor(() =>
        expect(result.current.childrenOf("V/B")).toMatchObject({ calculationId: "calc-2" }),
      );

      expect(calledPaths("calc-2").sort()).toEqual(["V", "V/B"]);
      expect(result.current.childrenOf("V/A")).toMatchObject({ calculationId: "calc-1" });
      expect(result.current.childrenOf("V/A/M")).toMatchObject({ calculationId: "calc-1" });

      await act(async () => result.current.toggle("V/A"));

      expect(result.current.isExpanded("V/A/M")).toBe(true);
      await waitFor(() => {
        for (const path of ["V/A", "V/A/M"]) {
          expect(result.current.childrenOf(path)).toMatchObject({
            status: "ready",
            calculationId: "calc-2",
          });
        }
      });
      expect(amountsOf(result, "V/A")).toEqual(["222.00"]);
      expect(amountsOf(result, "V/A/M")).toEqual(["222.00"]);
    });

    it("rouvrir un ancêtre recharge les sous-niveaux cachés, 4 au plus à la fois", async () => {
      const five = ["V/A", "V/B", "V/A/M", "V/B/M", "V/A/M/X"];
      localStorage.setItem("3istor.tree.bom-test", JSON.stringify(["V", ...five]));
      answerAtOnce();
      const { result, rerender } = mount("calc-1");
      await waitFor(() => expect(children).toHaveBeenCalledTimes(6));
      act(() => result.current.toggle("V"));

      rerender({ calculationId: "calc-2" });
      await act(async () => {});
      expect(calledPaths("calc-2")).toEqual([]);

      deferResponses();
      act(() => result.current.toggle("V"));
      for (let round = 0; round < 6; round++) {
        await waitFor(() => expect(pending.length).toBeGreaterThan(0));
        await act(async () => pending[0].resolve());
      }
      expect(pending).toHaveLength(0);

      expect(maxInFlight).toBe(4);
      expect(calledPaths("calc-2").sort()).toEqual(["V", ...five].sort());
      for (const path of ["V", ...five]) {
        expect(result.current.childrenOf(path)).toMatchObject({ calculationId: "calc-2" });
      }
    });

    it("un sous-niveau caché qui a disparu est élagué à la réouverture", async () => {
      localStorage.setItem(
        "3istor.tree.bom-test",
        JSON.stringify(["V", "V/B", "V/B/M"]),
      );
      answerAtOnce();
      const { result, rerender } = mount("calc-1");
      await waitFor(() => expect(children).toHaveBeenCalledTimes(3));
      act(() => result.current.toggle("V"));
      rerender({ calculationId: "calc-2" });

      children.mockImplementation(async (_version, path, calculationId) => {
        if (path === "V/B") throw { code: "PATH_NOT_FOUND", status: 404 };
        return page(path, calculationId);
      });
      await act(async () => result.current.toggle("V"));

      await waitFor(() => expect(result.current.isExpanded("V/B")).toBe(false));
      expect(result.current.isExpanded("V/B/M")).toBe(false);
      expect(result.current.isExpanded("V")).toBe(true);
      expect(stored()).toEqual(["V"]);
    });
  });
});

describe("useTreeState, snapshot de calcul ouvert", () => {
  function mountWithSnapshot(snapshotId: string | null) {
    return renderHook(
      (props: { snapshotId: string | null }) =>
        useTreeState({
          version: "bom-test",
          calculationId: "calc-1",
          snapshotId: props.snapshotId,
        }),
      { initialProps: { snapshotId } },
    );
  }

  it("demande les pages avec le snapshot ouvert", async () => {
    answerAtOnce();
    const { result } = mountWithSnapshot("csn-1");

    await act(async () => result.current.toggle("V"));

    expect(children.mock.calls).toEqual([["bom-test", "V", "calc-1", "csn-1"]]);
  });

  it("quitter le snapshot relit les pages, même sur le même calcul", async () => {
    answerAtOnce();
    const { result, rerender } = mountWithSnapshot("csn-1");
    await act(async () => result.current.toggle("V"));

    rerender({ snapshotId: null });

    await waitFor(() =>
      expect(children).toHaveBeenLastCalledWith("bom-test", "V", "calc-1"),
    );
    expect(children).toHaveBeenCalledTimes(2);
    expect(result.current.isExpanded("V")).toBe(true);
  });
});
