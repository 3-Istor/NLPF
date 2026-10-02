/**
 * Le cadre de l'application : quelle nomenclature est ouverte.
 *
 * Quatre nomenclatures coexistent — le Multipla et trois Valhalla. Le choix vit
 * dans l'URL (`?bom=`) : un F5 ou un lien partagé rouvre le même véhicule.
 * L'espace de travail est remonté à chaque changement : garder l'arbre, le
 * scénario ou le calcul d'un véhicule sous le nom d'un autre serait faux.
 *
 * Deux pages par véhicule : la nomenclature (arbre et synthèse) et ses
 * fournisseurs (`?page=fournisseurs`).
 */

import { useEffect, useState } from "react";
import { api, ApiFailure } from "./api/client";
import type { BomVersion } from "./api/types";
import { SuppliersPage } from "./components/SuppliersPage";
import { Workspace } from "./Workspace";

type Page = "nomenclature" | "fournisseurs";

function readPage(): Page {
  return new URLSearchParams(window.location.search).get("page") === "fournisseurs"
    ? "fournisseurs"
    : "nomenclature";
}

function writePage(page: Page) {
  const params = new URLSearchParams(window.location.search);
  if (page === "fournisseurs") params.set("page", page);
  else params.delete("page");
  const url = `${window.location.pathname}?${params}${window.location.hash}`;
  window.history.replaceState(window.history.state, "", url);
}

const DEFAULT_VERSION =
  import.meta.env.VITE_BOM_VERSION ?? "bom-multipla-2026-09-22";

/** Taux proposé quand la nomenclature ne dit pas le sien (base ancienne). */
const FALLBACK_LABOUR_RATE = "42.00";

function readBom(): string | null {
  return new URLSearchParams(window.location.search).get("bom");
}

/**
 * Changer de véhicule oublie le scénario et la ligne de l'URL : ils
 * appartiennent à l'ancien.
 */
function writeBom(version: string) {
  const params = new URLSearchParams(window.location.search);
  params.set("bom", version);
  params.delete("scenario");
  params.delete("node");
  params.delete("supplier");
  params.delete("part");
  const url = `${window.location.pathname}?${params}${window.location.hash}`;
  window.history.replaceState(window.history.state, "", url);
}

/** Le Multipla d'abord, puis les autres dans l'ordre de leur libellé. */
function ordered(items: BomVersion[]): BomVersion[] {
  return [...items]
    .filter((item) => item.validated_at !== null)
    .sort((a, b) =>
      a.id === DEFAULT_VERSION ? -1 : b.id === DEFAULT_VERSION ? 1 : a.label.localeCompare(b.label),
    );
}

export function App() {
  const [versions, setVersions] = useState<BomVersion[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [version, setVersion] = useState<string>(readBom() ?? DEFAULT_VERSION);
  const [page, setPage] = useState<Page>(readPage);

  useEffect(() => {
    let alive = true;
    api
      .bomVersions()
      .then(({ items }) => {
        if (!alive) return;
        const usable = ordered(items);
        setVersions(usable);
        // Un lien vers une nomenclature qui n'existe plus rouvre la première.
        if (usable.length > 0 && !usable.some((item) => item.id === version)) {
          setVersion(usable[0].id);
        }
      })
      .catch((error) => {
        if (!alive) return;
        // Sans la liste, on ouvre quand même la nomenclature demandée : le
        // sélecteur manque, pas l'écran.
        setVersions([]);
        setListError(describe(error));
      });
    return () => {
      alive = false;
    };
  }, []);

  function show(next: Page) {
    writePage(next);
    setPage(next);
  }

  function choose(next: string) {
    writeBom(next);
    setVersion(next);
  }

  const current = versions?.find((item) => item.id === version) ?? null;

  return (
    <div className="app">
      <nav className="shell" aria-label="Nomenclature">
        <h1>3istor</h1>
        {versions && versions.length > 0 ? (
          <label>
            Véhicule
            <select
              aria-label="Nomenclature ouverte"
              value={version}
              onChange={(event) => choose(event.target.value)}
            >
              {versions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} — {item.part_count} pièces
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span>{current?.label ?? version}</span>
        )}
        {current?.is_synthetic && (
          <span className="shell__synthetic">données synthétiques</span>
        )}
        <div className="shell__tabs" role="tablist" aria-label="Page">
          {(["nomenclature", "fournisseurs"] as const).map((choice) => (
            <button
              key={choice}
              type="button"
              role="tab"
              aria-selected={page === choice}
              onClick={() => show(choice)}
            >
              {choice === "nomenclature" ? "Nomenclature" : "Fournisseurs"}
            </button>
          ))}
        </div>
        {listError && (
          <span className="shell__error" role="status">
            liste des nomenclatures illisible : {listError}
          </span>
        )}
      </nav>
      {versions === null ? (
        <p className="hint">chargement des nomenclatures…</p>
      ) : page === "fournisseurs" ? (
        <SuppliersPage key={version} version={version} />
      ) : (
        <Workspace
          key={version}
          version={version}
          labourRate={current?.reference_labour_rate ?? FALLBACK_LABOUR_RATE}
        />
      )}
    </div>
  );
}

function describe(error: unknown): string {
  if (error instanceof ApiFailure) return `${error.code} — ${error.message}`;
  return error instanceof Error ? error.message : "erreur inconnue";
}
