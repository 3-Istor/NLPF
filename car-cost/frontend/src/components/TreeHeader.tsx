/** L'en-tête des colonnes de l'arbre ; il reste visible quand on défile. */

export function TreeHeader() {
  return (
    <div className="tree-header row-grid" role="row">
      <span role="columnheader">Pièce</span>
      <span role="columnheader">Réf.</span>
      <span role="columnheader" className="num" title="Quantité de cette pièce dans son parent direct">
        Qté / parent
      </span>
      <span role="columnheader" className="num" title="Quantité par véhicule en suivant ce chemin">
        Qté / véhicule
      </span>
      <span role="columnheader" className="num" title="Coût d'une unité de la pièce">
        Coût unitaire
      </span>
      <span
        role="columnheader"
        className="num"
        title="Ce que pèse cette occurrence, enfants compris, ne se somme pas"
      >
        Contribution
      </span>
      <span role="columnheader" className="num" title="Part du total du véhicule">
        Poids
      </span>
      <span role="columnheader">État</span>
    </div>
  );
}
