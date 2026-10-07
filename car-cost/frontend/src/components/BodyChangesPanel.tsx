/**
 * Le panneau « Variante » : le résultat d'un import, et l'écart de la variante
 * ouverte avec sa parente.
 *
 * Tout vient de l'API (`body-imports`, `body-changes`). Les écarts de masse et
 * de coût sont servis ; ce fichier les met en forme et ne calcule rien.
 */

import { ApiFailure } from "../api/client";
import type { BodyChanges, BodyImportResult, ImportFault } from "../api/types";
import { mass, money, quantity } from "../format";

type Props = {
  /** L'écart de la variante ouverte, `null` sur le véhicule d'origine. */
  changes: BodyChanges | null;
  /** Le dernier import tenté sur ce véhicule. */
  outcome: BodyImportResult | null;
  /** L'échec de l'import ou de la lecture de l'écart. */
  failure: unknown;
  onOpen: (versionId: string) => void;
};

export function BodyChangesPanel({ changes, outcome, failure, onOpen }: Props) {
  const shown = changes ?? outcome;
  const faults = failure instanceof ApiFailure ? (failure.details?.faults as ImportFault[] | undefined) : undefined;

  return (
    <section className="variant" aria-label="Variante de carrosserie">
      {failure !== null && (
        <div className="banner banner--danger" role="alert">
          {failure instanceof ApiFailure ? `${failure.code} : ${failure.message}` : String(failure)}
          {faults && (
            <ul>
              {faults.map((fault, index) => (
                <li key={index}>
                  <code>{fault.code}</code>, {fault.object} : {fault.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {outcome && (
        <p className="banner banner--live" role="status">
          {outcome.message}
          {outcome.variant && (
            <>
              {" "}
              <button type="button" onClick={() => onOpen(outcome.variant!.id)}>
                Ouvrir la variante
              </button>
            </>
          )}
        </p>
      )}

      {shown && (
        <>
          <dl className="variant__totals">
            <dt>Écart de coût</dt>
            <dd>
              {shown.cost ? (
                money(shown.cost.delta)
              ) : (
                <span className="hint hint--flush">prix indisponibles : figez les prix du Multipla</span>
              )}
            </dd>
            <dt>Écart de matière</dt>
            <dd>{mass(shown.material_mass_delta_kg)}</dd>
          </dl>

          <table className="variant__changes">
            <thead>
              <tr>
                <th>Pièce</th>
                <th>Matière</th>
                <th>Masse avant</th>
                <th>Masse après</th>
                <th>Écart</th>
              </tr>
            </thead>
            <tbody>
              {shown.changes.map((change) => (
                <tr key={change.part_ref}>
                  <td>
                    <code>{change.part_ref}</code>
                    <br />
                    {change.label} × {quantity(change.cumulative_quantity)}
                    {change.kind === "NEW" && " (nouvelle)"}
                  </td>
                  <td>
                    {change.material_before ? `${change.material_before} → ` : ""}
                    {change.material_after}
                  </td>
                  <td>{mass(change.mass_before_kg)}</td>
                  <td>{mass(change.mass_after_kg)}</td>
                  <td>{mass(change.mass_delta_kg)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
