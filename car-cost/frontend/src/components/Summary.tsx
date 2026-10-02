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
import { useState } from "react";
import { age, co2, money, percent, quantity } from "../format";
import { refusal } from "../quarantine";

type Props = {
  calculation: Calculation | null;
  /** `null` tant qu'il n'est pas lu, ou s'il n'a pas pu l'être. */
  journal: QuarantineJournal | null;
  /**
   * `FROZEN` : un snapshot de calcul ouvert, ni à jour ni obsolète.
   * `LIVE` : un calcul aux prix actuels de l'API, rafraîchi, jamais enregistré.
   */
  state: CalculationState | "FROZEN" | "LIVE";
  staleReason: string | null;
  busy: boolean;
  failure: string | null;
  onRecalculate: () => void;
  onGoToPath: (path: string) => void;
  onGoToPart: (partRef: string) => void;
};

const STATE_LABELS: Record<CalculationState | "FROZEN" | "LIVE", string> = {
  FROZEN: "figé",
  LIVE: "prix en direct",
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
  const stale = state !== "UP_TO_DATE" && state !== "FROZEN" && state !== "LIVE";
  const [chosenMetric, setMetric] = useState<"cost" | "co2">("cost");
  // Sans `total_co2`, les CO₂ par système sont des zéros de remplissage : on
  // ne propose pas de les regarder.
  const hasCo2 = calculation?.total_co2 != null;
  const metric = hasCo2 ? chosenMetric : "cost";

  return (
    <aside className="summary">
      <header className="summary__header">
        <h2>Synthèse</h2>
        <span
          className={`state state--${
            state === "FROZEN" ? "frozen" : state === "LIVE" ? "live" : stale ? "stale" : "fresh"
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
      {state === "LIVE" && (
        <p className="banner banner--live">
          Prix lus en direct sur l'API, rafraîchis toutes les 5 s : ce total
          n'est pas enregistré. Figez les prix pour le garder.
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

          {/* Le CO₂ peut être incomplet quand le coût ne l'est pas (prix forcé) :
              il porte son propre avertissement, sous son propre total. */}
          {calculation.total_co2 === null ? (
            <p className="total total--co2">
              <span className="total__label">Empreinte carbone</span>
              <span className="hint hint--flush">
                non calculée par ce calcul, antérieur au CO₂ : recalculer pour
                l'obtenir.
              </span>
            </p>
          ) : (
            <>
              <p className="total total--co2">
                <span className="total__label">
                  {calculation.parts_without_co2.length > 0
                    ? "Empreinte carbone partielle"
                    : "Empreinte carbone"}
                </span>
                <span className="total__value">{co2(calculation.total_co2)}</span>
              </p>
              {calculation.parts_without_co2.length > 0 && (
                <p className="banner banner--warn">
                  {calculation.parts_without_co2.length} pièce(s) sans CO₂ connu,
                  non comptées : sans prix, sans masse ou à prix forcé. Ce total
                  n'est pas l'empreinte du véhicule.
                </p>
              )}
            </>
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

          {hasCo2 && (
            <fieldset className="metric">
              <legend>Répartir par</legend>
              <label>
                <input
                  type="radio"
                  name="summary-metric"
                  checked={metric === "cost"}
                  onChange={() => setMetric("cost")}
                />
                Coût
              </label>
              <label>
                <input
                  type="radio"
                  name="summary-metric"
                  checked={metric === "co2"}
                  onChange={() => setMetric("co2")}
                />
                CO₂
              </label>
            </fieldset>
          )}

          <h3>Par système</h3>
          <ul className="systems">
            {calculation.systems.map((system) => {
              const share =
                metric === "co2" ? system.co2_share_pct : system.cost_share_pct;
              return (
                <li key={system.system}>
                  <span className="systems__name">{system.system}</span>
                  <span className="systems__bar">
                    <i
                      className={metric === "co2" ? "systems__bar--co2" : undefined}
                      style={{ width: `${share}%` }}
                    />
                  </span>
                  <span className="systems__value">
                    {metric === "co2" ? co2(system.co2) : money(system.cost)}
                  </span>
                  <span className="systems__pct">{percent(share)}</span>
                </li>
              );
            })}
          </ul>

          <h3>Principaux contributeurs</h3>
          <ul className="contributors">
            {(metric === "co2"
              ? calculation.top_co2_contributors.map((contributor) => ({
                  ...contributor,
                  value: co2(contributor.own_co2_contribution),
                }))
              : calculation.top_cost_contributors.map((contributor) => ({
                  ...contributor,
                  value: money(contributor.own_contribution),
                }))
            )
              .slice(0, 8)
              .map((contributor) => (
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
                  <span className="contributors__value">{contributor.value}</span>
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
