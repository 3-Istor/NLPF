/**
 * La synthèse, toujours visible.
 *
 * Elle affiche des chiffres venus de l'API, jamais recalculés ici. Tant que des
 * paramètres ont changé sans recalcul, les totaux sont marqués obsolètes :
 * montrer un ancien total comme s'il était frais est une faute, pas un détail
 * d'ergonomie.
 */

import type {
  Calculation,
  CalculationState,
  QuarantineJournal,
} from "../api/types";
import { age, money, percent, quantity } from "../format";
import { refusal } from "../quarantine";

type Props = {
  calculation: Calculation | null;
  /** `null` tant qu'il n'est pas lu, ou s'il n'a pas pu l'être. */
  journal: QuarantineJournal | null;
  /** `FROZEN` : un snapshot de calcul ouvert, ni à jour ni obsolète. */
  state: CalculationState | "FROZEN";
  staleReason: string | null;
  busy: boolean;
  failure: string | null;
  onRecalculate: () => void;
  onGoToPath: (path: string) => void;
  onGoToPart: (partRef: string) => void;
};

const STATE_LABELS: Record<CalculationState | "FROZEN", string> = {
  FROZEN: "figé",
  NEVER_RUN: "jamais calculé",
  UP_TO_DATE: "à jour",
  PARAMETERS_CHANGED: "totaux obsolètes",
  NO_PRICES: "aucun prix disponible",
};

export function Summary({
  calculation,
  journal,
  state,
  staleReason,
  busy,
  failure,
  onRecalculate,
  onGoToPath,
  onGoToPart,
}: Props) {
  // Un calcul figé ne vieillit pas : il ne se compare pas au scénario vivant.
  const stale = state !== "UP_TO_DATE" && state !== "FROZEN";

  return (
    <aside className="summary">
      <header className="summary__header">
        <h2>Synthèse</h2>
        <span
          className={`state state--${
            state === "FROZEN" ? "frozen" : stale ? "stale" : "fresh"
          }`}
        >
          {busy ? "calcul en cours…" : STATE_LABELS[state]}
        </span>
      </header>

      {stale && state === "PARAMETERS_CHANGED" && (
        <p className="banner banner--warn">
          {staleReason === "prices"
            ? "Les prix ont changé depuis ce calcul."
            : "Des paramètres ont changé depuis ce calcul."}{" "}
          Les montants ci-dessous ne sont plus à jour.
        </p>
      )}
      {state === "NO_PRICES" && (
        <p className="banner banner--danger">
          Aucun snapshot de prix disponible : aucun calcul n'est possible.
        </p>
      )}
      {failure && (
        <p className="banner banner--danger" role="alert">
          {failure}
        </p>
      )}

      <button className="recalc" onClick={onRecalculate} disabled={busy}>
        {calculation ? "Recalculer" : "Calculer"}
      </button>

      {calculation && (
        <div className={stale ? "figures figures--stale" : "figures"}>
          <p className="total">
            <span className="total__label">Coût de fabrication</span>
            <span className="total__value">{money(calculation.total_cost)}</span>
          </p>

          {calculation.status !== "OK" && (
            <p
              className={`banner banner--${
                calculation.status === "INCOMPLETE" ? "danger" : "warn"
              }`}
            >
              {calculation.status === "INCOMPLETE"
                ? `Total incomplet : ${calculation.parts_without_price.length} pièce(s) sans prix.`
                : degradedMessage(calculation)}
            </p>
          )}

          <dl className="snapshot">
            <dt>Prix utilisés</dt>
            <dd>
              <code>{calculation.price_snapshot.id}</code>
              <span
                className={
                  calculation.price_snapshot.status === "FRESH"
                    ? "chip"
                    : "chip chip--warn"
                }
              >
                {calculation.price_snapshot.status.toLowerCase()}
              </span>{" "}
              {age(calculation.price_snapshot.age_seconds)}
            </dd>
          </dl>

          {(calculation.issue_counts.quarantined > 0 ||
            (journal?.items.length ?? 0) > 0) && (
            <>
              <h3>Journal de quarantaine</h3>
              {journal ? (
                <ul className="quarantine">
                  {journal.items.map((entry, index) => (
                    <li key={`${entry.part_ref}-${entry.currency}-${index}`}>
                      <button
                        onClick={() => onGoToPart(entry.part_ref)}
                        title="Déplier l'arbre jusqu'à cette pièce"
                      >
                        {entry.part_ref}
                      </button>
                      <span className="quarantine__why">{refusal(entry)}</span>
                      <span className="quarantine__kept">
                        {entry.replacement
                          ? `référence retenue ${money(entry.replacement)}`
                          : "aucun prix retenu"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="hint hint--danger">
                  Le journal de quarantaine n'a pas pu être lu : les valeurs
                  refusées ne sont pas détaillées.
                </p>
              )}
            </>
          )}

          <h3>Par système</h3>
          <ul className="systems">
            {calculation.systems.map((system) => (
              <li key={system.system}>
                <span className="systems__name">{system.system}</span>
                <span className="systems__bar">
                  <i style={{ width: `${system.cost_share_pct}%` }} />
                </span>
                <span className="systems__value">{money(system.cost)}</span>
                <span className="systems__pct">
                  {percent(system.cost_share_pct)}
                </span>
              </li>
            ))}
          </ul>

          <h3>Principaux contributeurs</h3>
          <ul className="contributors">
            {calculation.top_cost_contributors.slice(0, 8).map((contributor) => (
              <li key={contributor.part_ref}>
                <button
                  onClick={() => onGoToPath(contributor.first_path)}
                  title="Déplier l'arbre jusqu'à cette pièce"
                >
                  {contributor.label}
                </button>
                <span className="contributors__qty">
                  × {quantity(contributor.cumulative_quantity)}
                </span>
                <span className="contributors__value">
                  {money(contributor.own_contribution)}
                </span>
              </li>
            ))}
          </ul>

          <p className="provenance">
            Calcul <code>{calculation.id}</code> · moteur{" "}
            <code>{calculation.bom_version}</code> · données{" "}
            <strong>plausibles mais synthétiques</strong>.
          </p>
        </div>
      )}
    </aside>
  );
}

/**
 * Combien de prix ne sont pas frais, et pourquoi. Les nombres viennent du
 * serveur : l'écran les cite, il ne les compte pas.
 */
function degradedMessage(calculation: Calculation): string {
  const { quarantined, fallback } = calculation.issue_counts;
  const kinds = [
    quarantined > 0 ? `${quarantined} prix en quarantaine` : null,
    fallback > 0 ? `${fallback} prix de repli` : null,
  ].filter((kind): kind is string => kind !== null);

  if (kinds.length === 0) {
    return "Prix dégradés : snapshot périmé, ou repris tel quel après une panne de l'API.";
  }
  return (
    `Prix dégradés : ${kinds.join(", ")}. Le dernier prix sain a été retenu ; ` +
    "les lignes concernées sont marquées dans l'arbre."
  );
}
