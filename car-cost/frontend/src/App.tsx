/**
 * L'écran principal : l'arbre à gauche, la synthèse à droite.
 *
 * Les deux zones sont visibles en même temps — l'utilisateur ne doit jamais
 * quitter l'arbre pour voir l'effet de ce qu'il vient de saisir.
 *
 * Tout chiffre affiché ici vient de l'API. Le seul calcul que ce fichier fait
 * est celui des positions à l'écran.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiFailure } from "./api/client";
import type {
  Calculation,
  CalculationSnapshot,
  CalculationSnapshotSummary,
  QuarantineJournal,
  Scenario,
  TreeLine,
} from "./api/types";
import { DecisionDialog } from "./components/DecisionDialog";
import { ScenarioBar } from "./components/ScenarioBar";
import { SearchBar } from "./components/SearchBar";
import { SnapshotHeader } from "./components/SnapshotHeader";
import { Summary } from "./components/Summary";
import { TreeHeader } from "./components/TreeHeader";
import { TreeToolbar } from "./components/TreeToolbar";
import { rowId, Tree } from "./components/Tree";
import { WhereUsed } from "./components/WhereUsed";
import { byPart, Refusals } from "./quarantine";
import { useTreeState } from "./tree/useTreeState";

const BOM_VERSION =
  import.meta.env.VITE_BOM_VERSION ?? "bom-multipla-2026-09-22";

/**
 * Le scénario et la ligne sélectionnée vivent dans l'URL : un F5 ou un lien
 * partagé rouvre le même endroit. `replaceState`, pas `pushState` : cliquer
 * une ligne ne doit pas remplir l'historique du bouton « Précédent ».
 */
function readLocation(): { scenario: string | null; node: string | null } {
  const params = new URLSearchParams(window.location.search);
  return { scenario: params.get("scenario"), node: params.get("node") };
}

function writeLocation(scenario: string, node: string | null) {
  const params = new URLSearchParams(window.location.search);
  params.set("scenario", scenario);
  if (node) params.set("node", node);
  else params.delete("node");
  const url = `${window.location.pathname}?${params}${window.location.hash}`;
  window.history.replaceState(window.history.state, "", url);
}

export function App() {
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [snapshots, setSnapshots] = useState<CalculationSnapshotSummary[]>([]);
  // Une liste illisible n'est pas une liste vide : on le dit.
  const [snapshotsError, setSnapshotsError] = useState<string | null>(null);
  // Le snapshot de calcul dont l'écran montre le calcul figé, en lecture
  // seule ; sinon, le scénario vivant, éditable.
  const [openSnapshot, setOpenSnapshot] = useState<CalculationSnapshot | null>(null);
  const [deciding, setDeciding] = useState(false);
  const [root, setRoot] = useState<TreeLine | null>(null);
  const [calculation, setCalculation] = useState<Calculation | null>(null);
  const [journal, setJournal] = useState<QuarantineJournal | null>(null);
  const refusals = useMemo(() => byPart(journal), [journal]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [whereUsed, setWhereUsed] = useState<string | null>(null);
  // La recherche en cours, surlignée dans l'arbre.
  const [query, setQuery] = useState("");
  const [initial] = useState(readLocation);
  const tree = useTreeState({
    version: BOM_VERSION,
    calculationId: calculation?.id ?? null,
    snapshotId: openSnapshot?.id ?? null,
    initialSelected: initial.node,
  });
  // La ligne de l'URL, à rouvrir puis à amener à l'écran une fois l'arbre là.
  const [pendingReveal, setPendingReveal] = useState(initial.node);
  const pendingScroll = useRef(initial.node);

  // Démarrage : on reprend le scénario de l'URL s'il appartient à cette
  // nomenclature, sinon le plus récent, sans rien signaler (un lien vers un
  // scénario supprimé n'est pas une erreur). On n'en crée un que s'il n'y en a
  // aucun : en créer un à chaque chargement remplirait la liste de scénarios
  // de travail vides.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { items } = await api.scenarios();
        let known = items.filter((item) => item.bom_version === BOM_VERSION);
        if (known.length === 0) {
          known = [
            await api.createScenario({
              bom_version: BOM_VERSION,
              name: "Scénario de travail",
              display_currency: "EUR",
              labour_rate: "42.00",
            }),
          ];
        }
        if (!alive) return;
        setScenarios(known);
        api
          .calculationSnapshots(BOM_VERSION)
          .then((page) => {
            if (!alive) return;
            setSnapshots(page.items);
            setSnapshotsError(null);
          })
          .catch((error) => alive && setSnapshotsError(describe(error)));
        await open(known.find((item) => item.id === initial.scenario) ?? known[0]);
      } catch (error) {
        if (alive) setFailure(describe(error));
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (scenario) writeLocation(scenario.id, tree.selected);
  }, [scenario, tree.selected]);

  // Déplier jusqu'à la ligne de l'URL attend la racine : avant, le calcul du
  // scénario ouvert n'est pas encore celui de l'arbre, et les pages demandées
  // seraient aussitôt périmées.
  const { reveal } = tree;
  useEffect(() => {
    if (!root || !pendingReveal) return;
    setPendingReveal(null);
    void reveal(pendingReveal);
  }, [root, pendingReveal, reveal]);

  // Puis on la montre, dès qu'elle est rendue.
  useEffect(() => {
    if (!pendingScroll.current) return;
    const row = document.getElementById(rowId(pendingScroll.current));
    if (!row) return;
    pendingScroll.current = null;
    row.scrollIntoView({ block: "center" });
  });

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
   * obsolète, la synthèse le grise comme après une modification. L'arbre garde
   * son dépliage et sa sélection : ses pages sont relues pour ce calcul.
   */
  async function open(next: Scenario, frozen: CalculationSnapshot | null = null) {
    const calculationId = frozen?.calculation_id ?? next.last_calculation_id;
    const last = calculationId ? await api.calculation(calculationId) : null;
    setScenario(next);
    setOpenSnapshot(frozen);
    setCalculation(last);
    setJournal(null);
    if (last) {
      api
        .quarantine(last.price_snapshot.id)
        .then(setJournal)
        .catch(() => setJournal(null));
    }
    // Ouvert, un snapshot marque ses lignes d'après sa copie des réglages.
    setRoot(
      await (frozen
        ? api.root(BOM_VERSION, last?.id ?? null, frozen.id)
        : api.root(BOM_VERSION, last?.id ?? null)),
    );
  }

  /** Quitte le snapshot ouvert : le scénario vivant, relu, redevient éditable. */
  async function backToScenario() {
    if (!scenario) return;
    setFailure(null);
    try {
      await open(await api.scenario(scenario.id));
    } catch (error) {
      setFailure(describe(error));
    }
  }

  /**
   * Lance un calcul sur le scénario vivant et le fige sous ce nom. Le résultat
   * affiché ensuite est celui du gel. Renvoie `false` si le serveur refuse
   * (nom déjà pris…) : le champ reste ouvert pour corriger le nom. Une fois le
   * gel fait, le champ se ferme quoi qu'il arrive : le rouvrir inviterait à
   * figer une seconde fois, et le serveur répondrait « nom déjà pris ».
   */
  async function freeze(name: string): Promise<boolean> {
    if (!scenario) return false;
    setBusy(true);
    setFailure(null);
    let frozen: CalculationSnapshot;
    try {
      frozen = await api.freezeCalculation(scenario.id, name);
    } catch (error) {
      setFailure(describe(error));
      setBusy(false);
      return false;
    }
    try {
      const fresh = await api.scenario(scenario.id);
      setScenarios((list) =>
        list.map((item) => (item.id === fresh.id ? fresh : item)),
      );
      await open(fresh, frozen);
      const page = await api.calculationSnapshots(BOM_VERSION);
      setSnapshots(page.items);
      setSnapshotsError(null);
    } catch (error) {
      setFailure(
        `Snapshot de calcul « ${frozen.name} » figé, mais l'écran n'a pas pu ` +
          `le rouvrir ou relire la liste : ${describe(error)}`,
      );
    } finally {
      setBusy(false);
    }
    return true;
  }

  /** Ouvre un calcul figé : son scénario, son calcul, son nom en en-tête. */
  async function openFrozen(id: string) {
    setFailure(null);
    try {
      const frozen = await api.calculationSnapshot(id);
      const owner =
        scenarios.find((item) => item.id === frozen.scenario_id) ??
        (await api.scenario(frozen.scenario_id));
      await open(owner, frozen);
    } catch (error) {
      setFailure(describe(error));
    }
  }

  /**
   * « Repartir de ce snapshot » : le scénario créé reprend exactement la copie
   * et s'ouvre éditable. Le snapshot d'origine n'est pas touché.
   */
  async function deriveFromSnapshot(name: string): Promise<string | null> {
    if (!openSnapshot) return null;
    let derived: Scenario;
    try {
      derived = await api.deriveScenario(openSnapshot.id, name);
    } catch (error) {
      return describe(error);
    }
    try {
      await reloadScenarios(derived.id);
    } catch (error) {
      // Le scénario existe : le dire, sans faire croire que la reprise a échoué.
      setFailure(`Scénario « ${derived.name} » créé ; ${describe(error)}`);
    }
    return null;
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
    setFailure(null);
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
      setOpenSnapshot(null);
      // Le journal éclaire le calcul sans le conditionner : s'il ne se lit
      // pas, la synthèse le dit, mais le total reste affiché.
      setJournal(null);
      api
        .quarantine(result.price_snapshot.id)
        .then(setJournal)
        .catch(() => setJournal(null));
      await refreshScenario();
      // Les lignes dépliées redemandent leurs chiffres d'elles-mêmes, sur le
      // changement de calcul ; seule la racine est relue ici.
      setRoot(await api.root(BOM_VERSION, result.id));
    } catch (error) {
      setFailure(describe(error));
    } finally {
      setBusy(false);
    }
  }

  function goToPath(path: string) {
    void reveal(path);
  }

  /**
   * Un résultat de recherche : déplier, sélectionner, puis centrer la ligne.
   * Si elle n'est pas encore rendue au retour de `reveal`, l'effet de
   * défilement la centre dès qu'elle l'est.
   */
  async function goToResult(path: string) {
    await reveal(path);
    const row = document.getElementById(rowId(path));
    if (row) row.scrollIntoView({ block: "center" });
    else pendingScroll.current = path;
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
        <ScenarioBar
          scenarios={scenarios}
          current={scenario}
          onSelect={(id) => selectScenario(id)}
          onDuplicate={duplicate}
          onDelete={removeScenario}
          onOpenDecision={() => setDeciding(true)}
          snapshots={snapshots}
          snapshotsError={snapshotsError}
          openSnapshotId={openSnapshot?.id ?? null}
          onFreeze={freeze}
          onOpenSnapshot={openFrozen}
        />
        {openSnapshot && (
          <SnapshotHeader
            key={openSnapshot.id}
            snapshot={openSnapshot}
            busy={busy}
            onBack={backToScenario}
            onDerive={deriveFromSnapshot}
          />
        )}
      </header>

      <main className="app__body">
        <section className="tree">
          {root ? (
            <Refusals.Provider value={refusals}>
              <div className="tree-head">
                <TreeToolbar onCollapseAll={tree.collapseAll}>
                  <SearchBar
                    version={BOM_VERSION}
                    onNavigate={goToResult}
                    onQueryChange={setQuery}
                  />
                </TreeToolbar>
                <TreeHeader />
              </div>
              <Tree
                root={root}
                state={tree}
                version={BOM_VERSION}
                scenario={openSnapshot ? null : scenario}
                frozen={openSnapshot}
                onParameterChanged={refreshScenario}
                onShowWhereUsed={setWhereUsed}
                query={query}
              />
            </Refusals.Provider>
          ) : (
            <p className="hint">{failure ?? "chargement de la nomenclature…"}</p>
          )}
        </section>

        <Summary
          calculation={calculation}
          journal={journal}
          state={
            openSnapshot ? "FROZEN" : (scenario?.calculation_state ?? "NEVER_RUN")
          }
          staleReason={openSnapshot ? null : (scenario?.stale_reason ?? null)}
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
          bomVersion={BOM_VERSION}
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
