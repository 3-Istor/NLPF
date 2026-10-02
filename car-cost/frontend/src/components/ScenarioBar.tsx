/**
 * Le scénario sur lequel on travaille, et les autres.
 *
 * Changer de scénario change tout ce qui est affiché : l'arbre, les marques
 * de modification, le total. L'écran repart donc sans calcul plutôt que de
 * montrer les chiffres d'un autre scénario sous un nouveau nom.
 *
 * La première entrée mène toujours à un scénario sans réglage : c'est la
 * référence contre laquelle on lit les variantes, elle ne doit pas disparaître
 * parce qu'on a réglé ou supprimé le scénario vide.
 */

import { useState } from "react";
import type { CalculationSnapshotSummary, Scenario } from "../api/types";

/** Aucun identifiant de scénario n'est vide : pas de collision possible. */
const BLANK_CHOICE = "";

type Props = {
  scenarios: readonly Scenario[];
  current: Scenario | null;
  onSelect: (id: string) => void;
  onSelectBlank: () => void;
  onDuplicate: (name: string) => void;
  onDelete: () => void;
  onOpenDecision: () => void;
  /** Les snapshots de calcul de cette version, du plus récent au plus ancien. */
  snapshots: readonly CalculationSnapshotSummary[];
  /** La liste n'a pas pu être lue : ce n'est pas une liste vide. */
  snapshotsError?: string | null;
  /** Le snapshot de calcul ouvert, s'il y en a un. */
  openSnapshotId: string | null;
  /** Fige sous ce nom ; `false` garde le champ ouvert (refus du serveur). */
  onFreeze: (name: string) => Promise<boolean | void> | boolean | void;
  onOpenSnapshot: (id: string) => void;
};

export function ScenarioBar({
  scenarios,
  current,
  onSelect,
  onSelectBlank,
  onDuplicate,
  onDelete,
  onOpenDecision,
  snapshots,
  snapshotsError = null,
  openSnapshotId,
  onFreeze,
  onOpenSnapshot,
}: Props) {
  const [copyName, setCopyName] = useState<string | null>(null);
  const [freezeName, setFreezeName] = useState<string | null>(null);
  const [freezeError, setFreezeError] = useState<string | null>(null);

  if (!current) return null;

  return (
    <div className="scenario-bar">
      <label>
        Scénario
        <select
          value={current.id}
          onChange={(event) =>
            event.target.value === BLANK_CHOICE
              ? onSelectBlank()
              : onSelect(event.target.value)
          }
        >
          <option value={BLANK_CHOICE}>Catalogue — sans réglage</option>
          {scenarios.map((scenario) => (
            <option key={scenario.id} value={scenario.id}>
              {scenario.name} ({scenario.parameters.length} réglage
              {scenario.parameters.length > 1 ? "s" : ""})
            </option>
          ))}
        </select>
      </label>

      {copyName === null ? (
        <button onClick={() => setCopyName("")}>
          Dupliquer
        </button>
      ) : (
        <form
          className="scenario-bar__copy"
          onSubmit={(event) => {
            event.preventDefault();
            if (!copyName.trim()) return;
            onDuplicate(copyName.trim());
            setCopyName(null);
          }}
        >
          <input
            aria-label="Nom de la copie"
            placeholder="Nom de la copie"
            value={copyName}
            onChange={(event) => setCopyName(event.target.value)}
            autoFocus
          />
          <button type="submit">Créer</button>
          <button type="button" onClick={() => setCopyName(null)}>
            Annuler
          </button>
        </form>
      )}

      {freezeName === null ? (
        <button
          onClick={() => {
            setFreezeError(null);
            // Le champ s'ouvre vide : le nom est celui que l'utilisateur
            // choisit, pas une proposition à corriger.
            setFreezeName("");
          }}
        >
          {/* Un snapshot ouvert ne se fige pas une seconde fois : figer capture
              toujours le scénario vivant, et le bouton le dit. */}
          {openSnapshotId ? "Figer le scénario vivant" : "Figer sous un nom"}
        </button>
      ) : (
        <form
          className="scenario-bar__copy"
          onSubmit={async (event) => {
            event.preventDefault();
            const name = freezeName.trim();
            if (!name) {
              setFreezeError("Le nom est obligatoire.");
              return;
            }
            setFreezeError(null);
            const result = await onFreeze(name);
            if (result !== false) setFreezeName(null);
          }}
        >
          <input
            aria-label="Nom du snapshot de calcul"
            placeholder="Nom du snapshot (obligatoire)"
            value={freezeName}
            onChange={(event) => setFreezeName(event.target.value)}
            autoFocus
          />
          <button type="submit">Figer</button>
          <button type="button" onClick={() => setFreezeName(null)}>
            Annuler
          </button>
          {freezeError && <span role="alert">{freezeError}</span>}
        </form>
      )}

      <select
        aria-label="Snapshots de calcul"
        value={openSnapshotId ?? ""}
        disabled={snapshots.length === 0}
        onChange={(event) => {
          if (event.target.value) onOpenSnapshot(event.target.value);
        }}
      >
        <option value="">
          {snapshotsError
            ? "Snapshots de calcul indisponibles"
            : snapshots.length === 0
              ? "Aucun snapshot de calcul"
              : "Ouvrir un snapshot de calcul…"}
        </option>
        {snapshots.map((snapshot) => (
          <option key={snapshot.id} value={snapshot.id}>
            {snapshot.name}
          </option>
        ))}
      </select>

      {snapshotsError && (
        <span role="alert" className="scenario-bar__error">
          Liste des snapshots de calcul illisible : {snapshotsError}
        </span>
      )}

      <button
        className="scenario-bar__danger"
        disabled={scenarios.length < 2}
        title={
          scenarios.length < 2
            ? "Le dernier scénario ne se supprime pas"
            : "Supprime le scénario, ses réglages et ses calculs"
        }
        onClick={() => {
          // Irréversible : les calculs partent avec le scénario.
          if (window.confirm(`Supprimer « ${current.name} » et ses calculs ?`)) {
            onDelete();
          }
        }}
      >
        Supprimer
      </button>

      <button className="scenario-bar__decide" onClick={onOpenDecision}>
        Comparer · Recommander
      </button>
    </div>
  );
}
