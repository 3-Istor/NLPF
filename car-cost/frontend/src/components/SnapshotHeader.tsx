/**
 * L'en-tête d'un snapshot de calcul ouvert.
 *
 * Un snapshot ne se modifie pas (ADR-0014) : on le quitte, ou on en repart
 * dans un scénario neuf qui reprend exactement sa copie. Ce scénario-là se
 * règle, et le figer produit un nouveau snapshot, aux prix du jour.
 */

import { useState } from "react";
import type { CalculationSnapshot } from "../api/types";

type Props = {
  snapshot: CalculationSnapshot;
  busy: boolean;
  onBack: () => void;
  /** Crée le scénario ; renvoie le refus à afficher, ou `null` s'il est créé. */
  onDerive: (name: string) => Promise<string | null>;
};

export function SnapshotHeader({ snapshot, busy, onBack, onDerive }: Props) {
  const [name, setName] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);

  return (
    <div className="snapshot-title">
      <p>
        Snapshot de calcul : <strong>{snapshot.name}</strong> — lecture seule,
        les réglages montrés sont ceux du gel.{" "}
        <button onClick={onBack} disabled={busy}>
          Revenir au scénario
        </button>{" "}
        {name === null && (
          <button
            onClick={() => {
              setRefusal(null);
              setName("");
            }}
            disabled={busy}
          >
            Repartir de ce snapshot
          </button>
        )}
      </p>
      {name !== null && (
        <form
          className="scenario-bar__copy"
          onSubmit={async (event) => {
            event.preventDefault();
            const chosen = name.trim();
            if (!chosen) {
              setRefusal("Le nom du scénario est obligatoire.");
              return;
            }
            const refused = await onDerive(chosen);
            setRefusal(refused);
            if (refused === null) setName(null);
          }}
        >
          <input
            aria-label="Nom du scénario repris"
            placeholder="Nom du nouveau scénario (obligatoire)"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoFocus
          />
          <button type="submit" disabled={busy}>
            Créer le scénario
          </button>
          <button type="button" onClick={() => setName(null)}>
            Annuler
          </button>
          {refusal && <span role="alert">{refusal}</span>}
        </form>
      )}
    </div>
  );
}
