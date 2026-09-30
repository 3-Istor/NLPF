/**
 * L'état de l'arbre, sorti des composants.
 *
 * Tant que chaque ligne gardait son dépliage pour elle, un recalcul remontait
 * l'arbre et tout se repliait. Ici, l'état appartient à l'écran : ce qui est
 * déplié le reste, et un recalcul redemande seulement les pages affichées pour
 * les remplacer en place.
 *
 * L'identité d'une ligne est son **chemin**, jamais sa référence : une pièce
 * partagée a une occurrence par parent, et chacune se déplie seule.
 *
 * Le hook ne calcule rien. Il remplace une page servie par une autre.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Page, TreeLine } from "../api/types";

export type ChildrenEntry =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; page: Page<TreeLine>; calculationId: string | null };

export type TreeState = {
  expanded: ReadonlySet<string>;
  selected: string | null;
  isExpanded(path: string): boolean;
  childrenOf(path: string): ChildrenEntry | undefined;
  toggle(path: string): void;
  select(path: string | null): void;
  collapseAll(): void;
  retry(path: string): void;
  reveal(path: string): Promise<void>;
};

export const STORAGE_PREFIX = "3istor.tree.";
export const REFRESH_CONCURRENCY = 4;

type Outcome = "ready" | "error" | "gone" | "stale";

type Expansion = { version: string; paths: ReadonlySet<string> };

function readStored(version: string): ReadonlySet<string> {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + version);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (Array.isArray(parsed)) {
      return new Set(parsed.filter((item): item is string => typeof item === "string"));
    }
  } catch {
    // Stockage absent, refusé ou illisible : on part d'un arbre replié.
  }
  return new Set();
}

function writeStored(version: string, paths: ReadonlySet<string>) {
  try {
    localStorage.setItem(STORAGE_PREFIX + version, JSON.stringify([...paths]));
  } catch {
    // Sans stockage, l'écran fonctionne ; seul le rechargement oublie.
  }
}

const isUnder = (path: string, ancestor: string) =>
  path === ancestor || path.startsWith(ancestor + "/");

function isPathGone(error: unknown): boolean {
  if (typeof error !== "object" || error === null) return false;
  const failure = error as { code?: unknown; status?: unknown };
  return failure.code === "PATH_NOT_FOUND" || failure.status === 404;
}

/** Les parents avant les enfants : l'écran se remplit de haut en bas. */
const byDepth = (a: string, b: string) => a.split("/").length - b.split("/").length;

export function useTreeState(options: {
  version: string;
  calculationId: string | null;
  initialSelected?: string | null;
}): TreeState {
  const { version, calculationId } = options;

  const [expansion, setExpansion] = useState<Expansion>(() => ({
    version,
    paths: readStored(version),
  }));
  const [selected, setSelected] = useState<string | null>(
    options.initialSelected ?? null,
  );
  const [entries, setEntries] = useState<ReadonlyMap<string, ChildrenEntry>>(
    () => new Map(),
  );

  // Ce que le rendu courant considère comme la vérité ; lu par les réponses
  // asynchrones pour savoir si elles sont encore attendues.
  const current = useRef({ version, calculationId });
  const expandedRef = useRef(expansion.paths);
  // Pour chaque chemin, le calcul de la dernière demande lancée ou servie.
  const requested = useRef(new Map<string, string | null>());

  useEffect(() => {
    expandedRef.current = expansion.paths;
    writeStored(expansion.version, expansion.paths);
  }, [expansion]);

  const setEntry = useCallback((path: string, entry: ChildrenEntry | null) => {
    setEntries((previous) => {
      const next = new Map(previous);
      if (entry === null) next.delete(path);
      else next.set(path, entry);
      return next;
    });
  }, []);

  const prune = useCallback((path: string) => {
    for (const known of [...requested.current.keys()]) {
      if (isUnder(known, path)) requested.current.delete(known);
    }
    setExpansion((previous) => ({
      version: previous.version,
      paths: new Set([...previous.paths].filter((known) => !isUnder(known, path))),
    }));
    setEntries((previous) => {
      const next = new Map(previous);
      for (const known of previous.keys()) if (isUnder(known, path)) next.delete(known);
      return next;
    });
  }, []);

  const needsLoad = useCallback(
    (path: string) =>
      !requested.current.has(path) ||
      requested.current.get(path) !== current.current.calculationId,
    [],
  );

  const load = useCallback(
    async (path: string): Promise<Outcome> => {
      const { version: forVersion, calculationId: forCalculation } = current.current;
      requested.current.set(path, forCalculation);
      // Au rafraîchissement, l'ancienne page reste affichée jusqu'à la nouvelle.
      setEntries((previous) => {
        if (previous.get(path)?.status === "ready") return previous;
        return new Map(previous).set(path, { status: "loading" });
      });

      const stillCurrent = () =>
        current.current.version === forVersion &&
        current.current.calculationId === forCalculation;

      try {
        const page = await api.children(forVersion, path, forCalculation);
        if (!stillCurrent()) return "stale";
        setEntry(path, { status: "ready", page, calculationId: forCalculation });
        return "ready";
      } catch (error) {
        if (!stillCurrent()) return "stale";
        if (isPathGone(error)) {
          prune(path);
          return "gone";
        }
        requested.current.delete(path);
        setEntry(path, {
          status: "error",
          message: error instanceof Error ? error.message : "échec du dépliage",
        });
        return "error";
      }
    },
    [prune, setEntry],
  );

  // Au montage, à chaque changement de calcul ou de nomenclature : on
  // redemande ce qui est déplié, jamais plus de REFRESH_CONCURRENCY à la fois.
  useEffect(() => {
    const versionChanged = current.current.version !== version;
    current.current = { version, calculationId };

    let paths = expandedRef.current;
    if (versionChanged) {
      paths = readStored(version);
      requested.current.clear();
      setEntries(new Map());
      setExpansion({ version, paths });
    }

    const queue = [...paths].filter(needsLoad).sort(byDepth);
    const worker = async () => {
      while (queue.length > 0) {
        if (
          current.current.version !== version ||
          current.current.calculationId !== calculationId
        ) {
          return;
        }
        await load(queue.shift()!);
      }
    };
    const workers = Math.min(REFRESH_CONCURRENCY, queue.length);
    for (let slot = 0; slot < workers; slot++) void worker();
  }, [version, calculationId, load, needsLoad]);

  const expand = useCallback((path: string) => {
    setExpansion((previous) =>
      previous.paths.has(path)
        ? previous
        : { version: previous.version, paths: new Set(previous.paths).add(path) },
    );
  }, []);

  const toggle = useCallback(
    (path: string) => {
      if (expandedRef.current.has(path)) {
        // Replier ferme aussi ce qui était ouvert dessous : ce qui est déplié
        // est exactement ce qui est affiché, donc ce qu'un recalcul redemande.
        const paths = new Set(
          [...expandedRef.current].filter((known) => !isUnder(known, path)),
        );
        expandedRef.current = paths;
        setExpansion((previous) => ({ version: previous.version, paths }));
        return;
      }
      expandedRef.current = new Set(expandedRef.current).add(path);
      expand(path);
      if (needsLoad(path)) void load(path);
    },
    [expand, load, needsLoad],
  );

  const collapseAll = useCallback(() => {
    expandedRef.current = new Set();
    setExpansion((previous) => ({ version: previous.version, paths: new Set() }));
  }, []);

  const retry = useCallback((path: string) => void load(path), [load]);

  const reveal = useCallback(
    async (path: string) => {
      const segments = path.split("/");
      for (let depth = 1; depth < segments.length; depth++) {
        const prefix = segments.slice(0, depth).join("/");
        expandedRef.current = new Set(expandedRef.current).add(prefix);
        expand(prefix);
        if (needsLoad(prefix) && (await load(prefix)) !== "ready") return;
      }
      setSelected(path);
    },
    [expand, load, needsLoad],
  );

  const expanded = expansion.paths;

  return useMemo(
    () => ({
      expanded,
      selected,
      isExpanded: (path: string) => expanded.has(path),
      childrenOf: (path: string) => entries.get(path),
      toggle,
      select: setSelected,
      collapseAll,
      retry,
      reveal,
    }),
    [expanded, selected, entries, toggle, collapseAll, retry, reveal],
  );
}
