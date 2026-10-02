/**
 * Compter ou non les pièces de rechange livrées avec le véhicule (SAV).
 *
 * L'écran n'additionne rien : il bascule le réglage, le serveur recalcule
 * les quantités. Sur une nomenclature sans SAV, l'interrupteur est grisé et
 * le dit, plutôt que de basculer sans effet.
 */

import type { Scenario } from "../api/types";

type Props = {
  scenario: Scenario;
  /** Un calcul figé est ouvert : ses réglages se lisent, ne se changent pas. */
  frozen: boolean;
  onChange: (include: boolean) => void;
};

export function AfterSalesToggle({ scenario, frozen, onChange }: Props) {
  const available = scenario.after_sales_available ?? false;
  const reason = !available
    ? "Cette nomenclature ne porte aucune pièce de rechange."
    : frozen
      ? "Calcul figé : ses réglages ne se modifient pas."
      : "Ajoute aux quantités montées les pièces livrées pour le SAV.";
  return (
    <label className="after-sales" title={reason}>
      <input
        type="checkbox"
        checked={scenario.include_after_sales ?? false}
        disabled={!available || frozen}
        onChange={(event) => onChange(event.target.checked)}
      />
      Inclure le SAV
      {!available && <span className="after-sales__none"> (aucun)</span>}
    </label>
  );
}
