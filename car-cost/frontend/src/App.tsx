/**
 * L'écran principal : l'arbre à gauche, la synthèse à droite.
 *
 * Les deux zones sont visibles en même temps — l'utilisateur ne doit jamais
 * quitter l'arbre pour voir l'effet de ce qu'il vient de saisir.
 *
 * Tout chiffre affiché ici vient de l'API. Le seul calcul que ce fichier fait
 * est celui des positions à l'écran.
 */

import { useCallback, useEffect, useState } from "react";
import { api, ApiFailure } from "./api/client";
import type { Calculation, Scenario, SearchHit, TreeLine } from "./api/types";
import { Summary } from "./components/Summary";
import { TreeNode } from "./components/TreeNode";
import { WhereUsed } from "./components/WhereUsed";

const BOM_VERSION =
  import.meta.env.VITE_BOM_VERSION ?? "bom-multipla-2026-09-22";

export function App() {
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [root, setRoot] = useState<TreeLine | null>(null);
  const [calculation, setCalculation] = useState<Calculation | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [whereUsed, setWhereUsed] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [expandTo, setExpandTo] = useState<string[] | undefined>();
  const [treeKey, setTreeKey] = useState(0);

  // Démarrage : un scénario de travail, et la racine de la nomenclature.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const created = await api.createScenario({
          bom_version: BOM_VERSION,
          name: "Scénario de travail",
          display_currency: "EUR",
          labour_rate: "42.00",
        });
        const line = await api.root(BOM_VERSION, null);
        if (!alive) return;
        setScenario(created);
        setRoot(line);
      } catch (error) {
        if (alive) setFailure(describe(error));
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const refreshScenario = useCallback(async () => {
    if (!scenario) return;
    setScenario(await api.scenario(scenario.id));
  }, [scenario]);

  async function recalculate() {
    if (!scenario) return;
    setBusy(true);
    setFailure(null);
    try {
      const result = await api.calculate(scenario.id);
      setCalculation(result);
      setScenario(await api.scenario(scenario.id));
      // Les lignes déjà dépliées portent les chiffres de l'ancien calcul :
      // on remonte l'arbre pour qu'elles redemandent les nouveaux.
      setTreeKey((key) => key + 1);
      setRoot(await api.root(BOM_VERSION, result.id));
    } catch (error) {
      setFailure(describe(error));
    } finally {
      setBusy(false);
    }
  }

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    const { items } = await api.search(BOM_VERSION, query.trim());
    setHits(items);
  }

  function goToPath(path: string) {
    setHits(null);
    setExpandTo(path.split("/"));
    setTreeKey((key) => key + 1);
  }

  return (
    <div className="app">
      <header className="app__header">
        <h1>3istor — Fiat Multipla 1.6 16V</h1>
        <form className="search" onSubmit={search}>
          <input
            type="search"
            placeholder="Chercher une référence ou un libellé…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit">Chercher</button>
        </form>
        <p className="disclaimer">
          Prix, masses et facteurs carbone <strong>synthétiques</strong> — aucune
          donnée constructeur.
        </p>
      </header>

      <main className="app__body">
        <section className="tree">
          {hits && (
            <div className="hits">
              <p>
                {hits.length} résultat(s)
                <button onClick={() => setHits(null)}>fermer</button>
              </p>
              <ul>
                {hits.map((hit) => (
                  <li key={hit.part_ref}>
                    <button onClick={() => goToPath(hit.paths[0])}>
                      {hit.label} <code>{hit.part_ref}</code>
                    </button>
                    <span>{hit.occurrence_count} emplacement(s)</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {root ? (
            <ul className="children" key={treeKey}>
              <TreeNode
                line={root}
                version={BOM_VERSION}
                scenarioId={scenario?.id ?? null}
                calculationId={calculation?.id ?? null}
                depth={0}
                expandTo={expandTo}
                onParameterChanged={refreshScenario}
                onShowWhereUsed={setWhereUsed}
              />
            </ul>
          ) : (
            <p className="hint">{failure ?? "chargement de la nomenclature…"}</p>
          )}
        </section>

        <Summary
          calculation={calculation}
          state={scenario?.calculation_state ?? "NEVER_RUN"}
          staleReason={scenario?.stale_reason ?? null}
          busy={busy}
          failure={failure}
          onRecalculate={recalculate}
          onGoToPath={goToPath}
        />
      </main>

      {whereUsed && (
        <WhereUsed
          version={BOM_VERSION}
          partRef={whereUsed}
          onClose={() => setWhereUsed(null)}
        />
      )}
    </div>
  );
}

function describe(error: unknown): string {
  if (error instanceof ApiFailure) return `${error.code} — ${error.message}`;
  return error instanceof Error ? error.message : "erreur inconnue";
}
