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
import type { Scenario } from "../api/types";

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
};

export function ScenarioBar({
  scenarios,
  current,
  onSelect,
  onSelectBlank,
  onDuplicate,
  onDelete,
  onOpenDecision,
}: Props) {
  const [copyName, setCopyName] = useState<string | null>(null);

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
        <button onClick={() => setCopyName(`${current.name} — variante`)}>
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
