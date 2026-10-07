/**
 * L'espace de travail d'une nomenclature : l'arbre à gauche, la synthèse à
 * droite.
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
  BodyChanges,
  BodyImportResult,
  Calculation,
  CalculationSnapshot,
  CalculationSnapshotSummary,
  PartCardData,
  QuarantineJournal,
  Scenario,
  TreeLine,
} from "./api/types";
import { AfterSalesToggle } from "./components/AfterSalesToggle";
import { BodyChangesPanel } from "./components/BodyChangesPanel";
import { LabourRateInput } from "./components/LabourRateInput";
import { DecisionDialog } from "./components/DecisionDialog";
import { PartCard } from "./components/PartCard";
import { PriceModeBar, type PriceMode } from "./components/PriceModeBar";
import { ScenarioBar } from "./components/ScenarioBar";
import { SearchBar } from "./components/SearchBar";
import { SnapshotHeader } from "./components/SnapshotHeader";
import { Summary } from "./components/Summary";
import { TreeHeader } from "./components/TreeHeader";
import { TreeToolbar } from "./components/TreeToolbar";
import { rowId, Tree } from "./components/Tree";
import { WhereUsed } from "./components/WhereUsed";
import { byPart, Refusals } from "./quarantine";
import { useTreeState, type TreeState } from "./tree/useTreeState";

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

interface WorkspaceProps {
  /** La nomenclature ouverte. Changer de nomenclature remonte l'écran. */
  version: string;
  /** Taux horaire proposé à la création d'un scénario sur cette nomenclature. */
  labourRate: string;
  /** Une variante de carrosserie : son CO₂ est masqué, son écart est lu à l'API. */
  isVariant: boolean;
  /** Ouvre une autre nomenclature, par exemple la variante qu'un import vient de créer. */
  onOpenVersion: (id: string) => void;
}

/** La ligne d'arbre d'un chemin, si sa page est chargée. De la navigation, pas un calcul. */
function lineAt(root: TreeLine, state: TreeState, path: string | null): TreeLine | null {
  if (path === null) return null;
  if (path === root.path) return root;
  const entry = state.childrenOf(path.slice(0, path.lastIndexOf("/")));
  return entry?.status === "ready" ? (entry.page.items.find((l) => l.path === path) ?? null) : null;
}

export function Workspace({ version, labourRate, isVariant, onOpenVersion }: WorkspaceProps) {
  const SCENARIO_DEFAULTS = {
    bom_version: version,
    display_currency: "EUR",
    labour_rate: labourRate,
  };

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
  // D'où viennent les prix : le snapshot (rejouable) ou l'API en direct.
  const [priceMode, setPriceMode] = useState<PriceMode>("SNAPSHOT");
  const [liveAt, setLiveAt] = useState<string | null>(null);
  // La recherche en cours, surlignée dans l'arbre.
  const [query, setQuery] = useState("");
  // Variante de carrosserie : l'écart servi par l'API et le dernier import tenté.
  const [changes, setChanges] = useState<BodyChanges | null>(null);
  const [outcome, setOutcome] = useState<BodyImportResult | null>(null);
  const [problem, setProblem] = useState<unknown>(null);
  const [importing, setImporting] = useState(false);
  const [tab, setTab] = useState<"summary" | "variant">("summary");
  const [card, setCard] = useState<{ path: string; data: PartCardData } | null>(null);
  const [initial] = useState(readLocation);
  const tree = useTreeState({
    version,
    calculationId: calculation?.id ?? null,
    snapshotId: openSnapshot?.id ?? null,
    initialSelected: initial.node,
  });
  const selectedLine = root ? lineAt(root, tree, tree.selected) : null;
  const selectedPath = selectedLine?.path ?? null;
  const selectedRef = selectedLine?.part_ref ?? null;
  const calculationId = calculation?.id ?? null;
  const change = changes?.changes.find((item) => item.part_ref === selectedRef);

  useEffect(() => {
    if (!isVariant) return;
    let alive = true;
    api
      .bodyChanges(version)
      .then((served) => alive && setChanges(served))
      .catch((error) => alive && setProblem(error));
    return () => {
      alive = false;
    };
  }, [isVariant, version]);

  // La fiche suit la ligne sélectionnée et le calcul affiché.
  useEffect(() => {
    if (selectedPath === null || selectedRef === null) return;
    let alive = true;
    api
      .partCard(version, selectedRef, calculationId)
      .then((data) => alive && setCard({ path: selectedPath, data }))
      .catch(() => alive && setCard(null));
    return () => {
      alive = false;
    };
  }, [version, selectedPath, selectedRef, calculationId]);

  async function importBody(file: File) {
    setImporting(true);
    setProblem(null);
    setTab("variant");
    try {
      const result = await api.bodyImport(version, file);
      setOutcome(result);
      if (result.status === "CREATED" && result.variant) onOpenVersion(result.variant.id);
    } catch (error) {
      setProblem(error);
    } finally {
      setImporting(false);
    }
  }

  // La ligne de l'URL, à rouvrir puis à amener à l'écran une fois l'arbre là.
  const [pendingReveal, setPendingReveal] = useState(initial.node);
  const pendingScroll = useRef(initial.node);
  const importInput = useRef<HTMLInputElement>(null);

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
        let known = items.filter((item) => item.bom_version === version);
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
        api
          .calculationSnapshots(version)
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

  // En direct : un calcul aux prix actuels de l'API toutes les 5 s, tant que
  // le mode dure et qu'aucun calcul figé n'est ouvert. Un changement de
  // scénario ou de réglage relance aussitôt la lecture.
  useEffect(() => {
    if (priceMode !== "LIVE" || !scenario || openSnapshot) return;
    let alive = true;
    const tick = async () => {
      try {
        const result = await api.calculateLive(scenario.id);
        if (!alive) return;
        setCalculation(result);
        setLiveAt(result.prices_taken_at ?? null);
        setJournal(null);
        setFailure(null);
        const fresh = await api.root(version, result.id);
        if (alive) setRoot(fresh);
      } catch (error) {
        if (alive) setFailure(describe(error));
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 5000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [priceMode, scenario, openSnapshot, version]);

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
    const known = items.filter((item) => item.bom_version === version);
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
        ? api.root(version, last?.id ?? null, frozen.id)
        : api.root(version, last?.id ?? null)),
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
      const page = await api.calculationSnapshots(version);
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

  /**
   * Le SAV change les quantités, le taux horaire le coût des ensembles : le
   * calcul affiché devient obsolète et la synthèse le grise, comme après tout
   * réglage.
   */
  async function saveSettings(change: (id: string) => Promise<Scenario>) {
    if (!scenario) return;
    setFailure(null);
    try {
      const fresh = await change(scenario.id);
      setScenario(fresh);
      setScenarios((list) =>
        list.map((item) => (item.id === fresh.id ? fresh : item)),
      );
    } catch (error) {
      setFailure(describe(error));
    }
  }

  /**
   * Revenir au mode snapshot rouvre le dernier calcul enregistré : un total
   * en direct ne doit pas rester affiché sous l'étiquette « à jour ».
   */
  async function changePriceMode(mode: PriceMode) {
    setPriceMode(mode);
    setLiveAt(null);
    if (mode === "SNAPSHOT" && scenario) {
      try {
        await open(await api.scenario(scenario.id));
      } catch (error) {
        setFailure(describe(error));
      }
    }
  }

  /** Fige les prix actuels de l'API, puis calcule dessus : un total rejouable. */
  async function freezePrices() {
    if (!scenario) return;
    setBusy(true);
    setFailure(null);
    try {
      await api.takePriceSnapshot(version, scenario.display_currency);
    } catch (error) {
      setFailure(describe(error));
      setBusy(false);
      return;
    }
    setPriceMode("SNAPSHOT");
    setLiveAt(null);
    setBusy(false);
    await recalculate();
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
      const known = items.filter((item) => item.bom_version === version);
      setScenarios(known);
      if (known.length > 0) await selectScenario(known[0].id, known);
    } catch (error) {
      setFailure(describe(error));
    }
  }

  async function recalculate() {
    if (!scenario) return;
    // « Recalculer » calcule sur le dernier snapshot : en direct, on en sort,
    // sinon le prochain rafraîchissement écraserait ce total.
    setPriceMode("SNAPSHOT");
    setLiveAt(null);
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
      setRoot(await api.root(version, result.id));
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
      const { items } = await api.whereUsed(version, partRef);
      if (items.length > 0) goToPath(items[0].path);
    } catch (error) {
      setFailure(describe(error));
    }
  }

  return (
    <div className="workspace">
      <header className="app__header">
        <ScenarioBar
          scenarios={scenarios}
          current={scenario}
          onSelect={(id) => selectScenario(id)}
          onSelectBlank={selectBlank}
          onDuplicate={duplicate}
          onDelete={removeScenario}
          onOpenDecision={() => setDeciding(true)}
          snapshots={snapshots}
          snapshotsError={snapshotsError}
          openSnapshotId={openSnapshot?.id ?? null}
          onFreeze={freeze}
          onOpenSnapshot={openFrozen}
        />
        {scenario && (
          <PriceModeBar
            mode={priceMode}
            frozen={openSnapshot !== null}
            busy={busy}
            liveAt={liveAt}
            onModeChange={(mode) => void changePriceMode(mode)}
            onFreezePrices={() => void freezePrices()}
          />
        )}
        {scenario && (
          <AfterSalesToggle
            scenario={scenario}
            frozen={openSnapshot !== null}
            onChange={(include) =>
              void saveSettings((id) => api.setAfterSales(id, include))
            }
          />
        )}
        {scenario && (
          <LabourRateInput
            scenario={scenario}
            frozen={openSnapshot !== null}
            onChange={(rate) =>
              void saveSettings((id) => api.setLabourRate(id, rate))
            }
          />
        )}
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
                    version={version}
                    onNavigate={goToResult}
                    onQueryChange={setQuery}
                  />
                </TreeToolbar>
                <TreeHeader />
              </div>
              <Tree
                root={root}
                state={tree}
                version={version}
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

        <div className="side">
          <div className="side__import">
            <button type="button" disabled={importing} onClick={() => importInput.current?.click()}>
              Importer une variante (.glb)
            </button>
            <input
              ref={importInput}
              type="file"
              accept=".glb"
              hidden
              aria-label="Fichier .glb"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void importBody(file);
              }}
            />
          </div>
          {(isVariant || outcome || problem !== null) && (
            <div className="shell__tabs" role="tablist" aria-label="Panneau de droite">
              {(["summary", "variant"] as const).map((choice) => (
                <button
                  key={choice}
                  type="button"
                  role="tab"
                  aria-selected={tab === choice}
                  onClick={() => setTab(choice)}
                >
                  {choice === "summary" ? "Synthèse" : "Variante"}
                </button>
              ))}
            </div>
          )}
          {tab === "variant" ? (
            <BodyChangesPanel changes={changes} outcome={outcome} failure={problem} onOpen={onOpenVersion} />
          ) : (
            <Summary
              calculation={calculation}
              journal={journal}
              state={
                openSnapshot
                  ? "FROZEN"
                  : priceMode === "LIVE"
                    ? "LIVE"
                    : (scenario?.calculation_state ?? "NEVER_RUN")
              }
              staleReason={openSnapshot ? null : (scenario?.stale_reason ?? null)}
              busy={busy}
              failure={failure}
              hideCo2={isVariant}
              onRecalculate={recalculate}
              onGoToPath={goToPath}
              onGoToPart={goToPart}
            />
          )}
          {selectedLine && card?.path === selectedLine.path && (
            <PartCard card={card.data} line={selectedLine} change={change} />
          )}
        </div>
      </main>

      {deciding && scenario && (
        <DecisionDialog
          scenarios={scenarios}
          current={scenario}
          bomVersion={version}
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
          version={version}
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
