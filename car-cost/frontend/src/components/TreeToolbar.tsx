/** La barre au-dessus de l'arbre : replier, et (plus tard) le compteur de recherche. */

type Props = {
  onCollapseAll: () => void;
};

export function TreeToolbar({ onCollapseAll }: Props) {
  return (
    <div className="tree-toolbar">
      <button onClick={onCollapseAll}>Tout replier</button>
      {/* Emplacement du compteur de recherche. */}
      <span className="tree-toolbar__search" />
    </div>
  );
}
