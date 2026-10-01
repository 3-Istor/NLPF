/**
 * L'écran principal : l'arbre à gauche, la synthèse à droite.
 *
 * Les deux zones sont visibles en même temps — l'utilisateur ne doit jamais
 * quitter l'arbre pour voir l'effet de ce qu'il vient de saisir.
 *
 * Tout chiffre affiché ici vient de l'API. Le seul calcul que ce fichier fait
 * est celui des positions à l'écran.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiFailure } from "./api/client";
import type {
  Calculation,
  QuarantineJournal,
  Scenario,
  SearchHit,
  TreeLine,
} from "./api/types";
import { DecisionDialog } from "./components/DecisionDialog";
import { ScenarioBar } from "./components/ScenarioBar";
import { Summary } from "./components/Summary";
import { TreeNode } from "./components/TreeNode";
import { WhereUsed } from "./components/WhereUsed";
import { byPart, Refusals } from "./quarantine";

const BOM_VERSION =
  import.meta.env.VITE_BOM_VERSION ?? "bom-multipla-2026-09-22";

const SCENARIO_DEFAULTS = {
  bom_version: BOM_VERSION,
  display_currency: "EUR",
  labour_rate: "42.00",
};

export function App() {
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [deciding, setDeciding] = useState(false);
  const [root, setRoot] = useState<TreeLine | null>(null);
  const [calculation, setCalculation] = useState<Calculation | null>(null);
  const [journal, setJournal] = useState<QuarantineJournal | null>(null);
  const refusals = useMemo(() => byPart(journal), [journal]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [whereUsed, setWhereUsed] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [expandTo, setExpandTo] = useState<string[] | undefined>();
  const [treeKey, setTreeKey] = useState(0);

  // Démarrage : on reprend le scénario le plus récent de cette nomenclature,
  // et on n'en crée un que s'il n'y en a aucun. En créer un à chaque
  // chargement remplirait la liste de scénarios de travail vides.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { items } = await api.scenarios();
        let known = items.filter((item) => item.bom_version === BOM_VERSION);
        if (known.length === 0) {
          known = [
            await api.createScenario({
              ...SCENARIO_DEFAULTS,
              name: "Scénario de travail",
            }),
          ];
        }
        if (!alive) return;
        setScenarios(known);
        await open(known[0]);
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
    const fresh = await api.scenario(scenario.id);
    setScenario(fresh);
    setScenarios((list) =>
      list.map((item) => (item.id === fresh.id ? fresh : item)),
    );
  }, [scenario]);

  async function reloadScenarios(selectId?: string) {
    const { items } = await api.scenarios();
    const known = items.filter((item) => item.bom_version === BOM_VERSION);
    setScenarios(known);
    if (selectId) await selectScenario(selectId, known);
  }

  /**
   * Un autre scénario : on repart sans calcul. Garder le total précédent
   * afficherait les chiffres d'un scénario sous le nom d'un autre.
   */
  async function selectScenario(id: string, list: Scenario[] = scenarios) {
    setFailure(null);
    try {
      await open(list.find((item) => item.id === id) ?? (await api.scenario(id)));
    } catch (error) {
      setFailure(describe(error));
    }
  }

  /**
   * Affiche un scénario avec son dernier calcul, relu et non relancé. S'il est
   * obsolète, la synthèse le grise comme après une modification.
   */
  async function open(next: Scenario) {
    const last = next.last_calculation_id
      ? await api.calculation(next.last_calculation_id)
      : null;
    setScenario(next);
    setCalculation(last);
    setJournal(null);
    if (last) {
      api
        .quarantine(last.price_snapshot.id)
        .then(setJournal)
        .catch(() => setJournal(null));
    }
    setExpandTo(undefined);
    setTreeKey((key) => key + 1);
    setRoot(await api.root(BOM_VERSION, last?.id ?? null));
  }

  /**
   * Le point de départ sans aucun réglage doit rester accessible même après
   * avoir réglé ou supprimé le scénario vide du démarrage. On rouvre le plus
   * récent qui existe et on n'en crée un que s'il n'y en a plus, pour ne pas
   * empiler des scénarios vides identiques.
   */
  async function selectBlank() {
    setFailure(null);
    try {
      const existing = scenarios.find((item) => item.parameters.length === 0);
      if (existing) {
        await open(existing);
        return;
      }
      const created = await api.createScenario({
        ...SCENARIO_DEFAULTS,
        name: "Catalogue — sans réglage",
      });
      await reloadScenarios(created.id);
    } catch (error) {
      setFailure(describe(error));
    }
  }

  async function duplicate(name: string) {
    if (!scenario) return;
    try {
      const copy = await api.duplicateScenario(scenario.id, name);
      await reloadScenarios(copy.id);
    } catch (error) {
      setFailure(describe(error));
    }
  }

  async function removeScenario() {
    if (!scenario) return;
    try {
      await api.deleteScenario(scenario.id);
      const { items } = await api.scenarios();
      const known = items.filter((item) => item.bom_version === BOM_VERSION);
      setScenarios(known);
      if (known.length > 0) await selectScenario(known[0].id, known);
    } catch (error) {
      setFailure(describe(error));
    }
  }

  async function recalculate() {
    if (!scenario) return;
    setBusy(true);
    setFailure(null);
    try {
      const result = await api.calculate(scenario.id);
      setCalculation(result);
      // Le journal éclaire le calcul sans le conditionner : s'il ne se lit
      // pas, la synthèse le dit, mais le total reste affiché.
      setJournal(null);
      api
        .quarantine(result.price_snapshot.id)
        .then(setJournal)
        .catch(() => setJournal(null));
      await refreshScenario();
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

  /** Une pièce du journal : le serveur dit où elle est montée, on y va. */
  async function goToPart(partRef: string) {
    try {
      const { items } = await api.whereUsed(BOM_VERSION, partRef);
      if (items.length > 0) goToPath(items[0].path);
    } catch (error) {
      setFailure(describe(error));
    }
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
        <ScenarioBar
          scenarios={scenarios}
          current={scenario}
          onSelect={(id) => selectScenario(id)}
          onSelectBlank={selectBlank}
          onDuplicate={duplicate}
          onDelete={removeScenario}
          onOpenDecision={() => setDeciding(true)}
        />
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
            <Refusals.Provider value={refusals}>
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
            </Refusals.Provider>
          ) : (
            <p className="hint">{failure ?? "chargement de la nomenclature…"}</p>
          )}
        </section>

        <Summary
          calculation={calculation}
          journal={journal}
          state={scenario?.calculation_state ?? "NEVER_RUN"}
          staleReason={scenario?.stale_reason ?? null}
          busy={busy}
          failure={failure}
          onRecalculate={recalculate}
          onGoToPath={goToPath}
          onGoToPart={goToPart}
        />
      </main>

      {deciding && scenario && (
        <DecisionDialog
          scenarios={scenarios}
          current={scenario}
          onClose={() => setDeciding(false)}
          onGoToPart={(partRef) => {
            setDeciding(false);
            goToPart(partRef);
          }}
          onCreated={() => reloadScenarios()}
          onOpenScenario={(id) => {
            setDeciding(false);
            selectScenario(id);
          }}
        />
      )}

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
