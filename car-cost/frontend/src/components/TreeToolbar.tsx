/** La barre au-dessus de l'arbre : replier, et la recherche avec son compteur. */

import type { ReactNode } from "react";

type Props = {
  onCollapseAll: () => void;
  /** La recherche, posée à droite de la barre. */
  children?: ReactNode;
};

export function TreeToolbar({ onCollapseAll, children }: Props) {
  return (
    <div className="tree-toolbar">
      <button onClick={onCollapseAll}>Tout replier</button>
      <div className="tree-toolbar__search">{children}</div>
    </div>
  );
}
