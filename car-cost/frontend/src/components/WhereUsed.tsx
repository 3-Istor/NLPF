/**
 * Où cette pièce est-elle montée ?
 *
 * Sans cette vue, la répétition d'une pièce partagée dans l'arbre passe pour un
 * doublon de données, et l'utilisateur cesse de faire confiance à l'outil.
 */

import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Occurrence } from "../api/types";
import { quantity } from "../format";

type Props = {
  version: string;
  partRef: string;
  onClose: () => void;
};

export function WhereUsed({ version, partRef, onClose }: Props) {
  const [items, setItems] = useState<Occurrence[] | null>(null);
  const [total, setTotal] = useState(0);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setItems(null);
    setFailure(null);
    api
      .whereUsed(version, partRef)
      .then((page) => {
        if (!alive) return;
        setItems([...page.items]);
        setTotal(page.occurrence_count);
      })
      .catch((error) => {
        if (!alive) return;
        setFailure(
          error instanceof Error ? error.message : "échec du chargement",
        );
      });
    return () => {
      alive = false;
    };
  }, [version, partRef]);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(event) => event.stopPropagation()}>
        <header>
          <h3>
            <code>{partRef}</code> : {total} emplacement(s)
          </h3>
          <button onClick={onClose}>Fermer</button>
        </header>
        {failure !== null ? (
          <p className="banner banner--danger" role="alert">
            {failure}
          </p>
        ) : items === null ? (
          <p className="hint">chargement…</p>
        ) : (
          <>
            {items.length < total && (
              <p className="hint">
                {items.length} emplacements sur {total}
              </p>
            )}
            <ol className="paths">
              {items.map((occurrence) => (
                <li key={occurrence.path}>
                  <span className="paths__labels">
                    {occurrence.path_labels.join(" › ")}
                  </span>
                  <span className="paths__qty">
                    {quantity(occurrence.quantity_on_path)} par véhicule
                  </span>
                </li>
              ))}
            </ol>
          </>
        )}
        <p className="hint">
          Ces lignes sont la même pièce, montée à plusieurs endroits, pas un
          doublon.
        </p>
      </div>
    </div>
  );
}
