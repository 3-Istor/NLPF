/**
 * La fiche d'une pièce : trois réponses de l'API côte à côte (fiche, ligne
 * d'arbre, écart de la variante). Aucune opération : un coût qui ne se lit
 * pas dans une réponse ne s'affiche pas.
 */

import type { PartCardData, PartChange, TreeLine } from "../api/types";
import { mass, money, quantity } from "../format";

type Props = {
  card: PartCardData;
  /** La ligne d'arbre sélectionnée : la quantité unitaire est celle de son arête. */
  line: TreeLine;
  /** Présent sur une variante, pour une pièce modifiée ou nouvelle. */
  change?: PartChange;
};

export function PartCard({ card, line, change }: Props) {
  // Les écarts servis sont des montants nus : la devise est celle de la fiche.
  const served = (amount: string | null): string =>
    amount !== null && card.unit_cost ? money({ amount, currency: card.unit_cost.currency }) : "—";

  return (
    <section className="part-card" aria-label="Fiche pièce">
      <h3>
        {card.label} <code>{card.part_ref}</code>
      </h3>
      <dl>
        <dt>Matière</dt>
        <dd>{card.material_ref ?? "—"}</dd>
        <dt>Masse</dt>
        <dd>
          {mass(card.material_quantity_kg)}
          {card.mass_kg !== null && card.mass_kg !== card.material_quantity_kg && (
            <> (masse de la pièce : {mass(card.mass_kg)})</>
          )}
        </dd>
        <dt>Quantité unitaire</dt>
        <dd>× {quantity(line.edge_quantity, line.unit)}</dd>
        <dt>Quantité cumulée</dt>
        <dd>{quantity(card.cumulative_quantity ?? undefined)}</dd>
        <dt>Coût unitaire</dt>
        <dd>{money(card.unit_cost)}</dd>
        <dt>Contribution propre</dt>
        <dd>{money(card.own_contribution)}</dd>
      </dl>

      {card.composition.length > 0 && (
        <>
          <h4>Composition</h4>
          <ul>
            {card.composition.map((child) => (
              <li key={child.part_ref}>
                <code>{child.part_ref}</code> {child.label} × {quantity(child.quantity, child.unit)}
              </li>
            ))}
          </ul>
        </>
      )}

      {change && (
        <div className="part-card__variant">
          {change.kind === "NEW" ? (
            <p>nouvelle pièce, absente de la parente</p>
          ) : (
            <>
              <h4>Avant → après</h4>
              <dl>
                <dt>Matière</dt>
                <dd>
                  <span>{change.material_before}</span> → <span>{change.material_after}</span>
                </dd>
                <dt>Masse</dt>
                <dd>
                  <span>{mass(change.mass_before_kg)}</span> → <span>{mass(change.mass_after_kg)}</span>
                </dd>
                <dt>Coût unitaire</dt>
                <dd>
                  <span>{served(change.unit_cost_before)}</span> → <span>{served(change.unit_cost_after)}</span>
                </dd>
              </dl>
            </>
          )}
        </div>
      )}
    </section>
  );
}
