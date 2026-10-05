/**
 * Le taux horaire du scénario : le coût d'une heure de main-d'œuvre sur
 * chaque ensemble fabriqué.
 *
 * La saisie part au serveur telle quelle, en chaîne : c'est lui qui la
 * valide et la multiplie par les temps, pas l'écran.
 */

import { useState } from "react";
import type { Scenario } from "../api/types";
import { editable } from "../format";

type Props = {
  scenario: Scenario;
  /** Un calcul figé est ouvert : ses réglages se lisent, ne se changent pas. */
  frozen: boolean;
  onChange: (rate: string) => void;
};

export function LabourRateInput({ scenario, frozen, onChange }: Props) {
  // La clé remet le brouillon à la valeur enregistrée quand le scénario change.
  return (
    <RateField
      key={`${scenario.id}:${scenario.labour_rate}`}
      saved={scenario.labour_rate}
      currency={scenario.display_currency}
      frozen={frozen}
      onChange={onChange}
    />
  );
}

function RateField({
  saved,
  currency,
  frozen,
  onChange,
}: {
  saved: string;
  currency: string;
  frozen: boolean;
  onChange: (rate: string) => void;
}) {
  const [draft, setDraft] = useState(editable(saved));
  const commit = () => {
    const rate = draft.trim().replace(",", ".");
    if (rate && rate !== editable(saved)) onChange(rate);
  };
  return (
    <label className="after-sales">
      Taux horaire
      <input
        type="text"
        inputMode="decimal"
        size={7}
        value={draft}
        disabled={frozen}
        title={
          frozen
            ? "Calcul figé : ses réglages ne se modifient pas."
            : "Coût d'une heure de main-d'œuvre sur les ensembles fabriqués."
        }
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => event.key === "Enter" && commit()}
      />
      {currency}/h
    </label>
  );
}
