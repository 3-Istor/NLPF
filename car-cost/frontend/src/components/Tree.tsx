/**
 * L'arbre, à partir de sa racine.
 *
 * Il ne garde rien : dépliage, pages chargées et sélection vivent dans le
 * `TreeState` de l'écran, qui survit au recalcul. Ce composant se contente de
 * rendre ce que l'état contient.
 *
 * Il se pilote au clavier selon le motif WAI-ARIA « tree » : une seule ligne
 * atteignable par Tab (la sélectionnée, sinon la racine), les flèches pour
 * parcourir, déplier et replier, Entrée pour ouvrir le panneau de saisie.
 */

import { useState, type KeyboardEvent } from "react";
import type { Scenario, TreeLine } from "../api/types";
import type { TreeState } from "../tree/useTreeState";
import { rowId } from "./rowId";
import { TreeNode } from "./TreeNode";

// Défini à part pour que Tree et TreeNode ne s'importent pas mutuellement.
export { rowId } from "./rowId";

type Props = {
  root: TreeLine;
  state: TreeState;
  version: string;
  scenario: Scenario | null;
  onParameterChanged: () => void;
  onShowWhereUsed: (partRef: string) => void;
};

type VisibleRow = { line: TreeLine; parent: string | null };

/**
 * Les lignes affichées, dans l'ordre de l'écran : celles des pages servies
 * sous des lignes dépliées. De la navigation, pas un calcul.
 */
function visibleRows(root: TreeLine, state: TreeState): VisibleRow[] {
  const rows: VisibleRow[] = [];
  const walk = (line: TreeLine, parent: string | null) => {
    rows.push({ line, parent });
    if (!state.isExpanded(line.path)) return;
    const entry = state.childrenOf(line.path);
    if (entry?.status !== "ready") return;
    for (const child of entry.page.items) walk(child, line.path);
  };
  walk(root, null);
  return rows;
}

const focusRow = (path: string) => document.getElementById(rowId(path))?.focus();

export function Tree({
  root,
  state,
  version,
  scenario,
  onParameterChanged,
  onShowWhereUsed,
}: Props) {
  // La ligne atteinte au clavier et pas encore ouverte : la sélection suit le
  // focus, mais le panneau attend Entrée pour ne pas s'ouvrir à chaque flèche.
  const [browsed, setBrowsed] = useState<string | null>(null);

  const rows = visibleRows(root, state);
  const tabStop = rows.some((row) => row.line.path === state.selected)
    ? state.selected!
    : root.path;

  const moveTo = (path: string) => {
    state.select(path);
    setBrowsed(path);
    focusRow(path);
  };

  function onKeyDown(event: KeyboardEvent<HTMLUListElement>) {
    const target = event.target as HTMLElement;
    const item = target.closest<HTMLElement>('[role="treeitem"]');
    if (!item || !event.currentTarget.contains(item)) return;
    const index = rows.findIndex((row) => rowId(row.line.path) === item.id);
    if (index < 0) return;
    const { line, parent } = rows[index];
    const open = state.isExpanded(line.path);

    switch (event.key) {
      case "ArrowDown":
        if (index + 1 < rows.length) moveTo(rows[index + 1].line.path);
        break;
      case "ArrowUp":
        if (index > 0) moveTo(rows[index - 1].line.path);
        break;
      case "ArrowRight":
        if (!line.has_children) break;
        if (!open) state.toggle(line.path);
        else if (rows[index + 1]?.parent === line.path) moveTo(rows[index + 1].line.path);
        break;
      case "ArrowLeft":
        if (line.has_children && open) state.toggle(line.path);
        else if (parent !== null) moveTo(parent);
        break;
      case "Enter":
        // Sur un bouton de la ligne, Entrée garde son effet natif.
        if (target !== item) return;
        state.select(line.path);
        setBrowsed(null);
        break;
      case "*":
        for (const row of rows) {
          if (
            row.parent === parent &&
            row.line.has_children &&
            !state.isExpanded(row.line.path)
          ) {
            state.toggle(row.line.path);
          }
        }
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  return (
    <ul className="children" role="tree" aria-label="Nomenclature" onKeyDown={onKeyDown}>
      <TreeNode
        line={root}
        depth={0}
        state={state}
        version={version}
        scenario={scenario}
        tabStop={tabStop}
        browsed={browsed}
        onOpenPanel={() => setBrowsed(null)}
        onParameterChanged={onParameterChanged}
        onShowWhereUsed={onShowWhereUsed}
      />
    </ul>
  );
}
