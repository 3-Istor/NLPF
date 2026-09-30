/**
 * L'arbre, à partir de sa racine.
 *
 * Il ne garde rien : dépliage, pages chargées et sélection vivent dans le
 * `TreeState` de l'écran, qui survit au recalcul. Ce composant se contente de
 * rendre ce que l'état contient.
 */

import type { Scenario, TreeLine } from "../api/types";
import type { TreeState } from "../tree/useTreeState";
import { TreeNode } from "./TreeNode";

/** L'id DOM d'une ligne : son chemin, qui est son identité (DAG). */
export const rowId = (path: string) => `node-${path}`;

type Props = {
  root: TreeLine;
  state: TreeState;
  version: string;
  scenario: Scenario | null;
  onParameterChanged: () => void;
  onShowWhereUsed: (partRef: string) => void;
};

export function Tree({
  root,
  state,
  version,
  scenario,
  onParameterChanged,
  onShowWhereUsed,
}: Props) {
  return (
    <ul className="children">
      <TreeNode
        line={root}
        depth={0}
        state={state}
        version={version}
        scenario={scenario}
        onParameterChanged={onParameterChanged}
        onShowWhereUsed={onShowWhereUsed}
      />
    </ul>
  );
}
