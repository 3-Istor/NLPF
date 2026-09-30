/**
 * L'aide à la décision : comparer deux scénarios, recommander un sourcing.
 *
 * Tous les écarts, totaux et économies viennent de l'API (ADR-0012). L'écran
 * n'additionne pas les économies des lignes cochées : l'économie de la
 * variante est annoncée par le serveur une fois la variante calculée.
 */

import { useState } from "react";
import { api, ApiFailure } from "../api/client";
import type {
  Comparison,
  Scenario,
  SourcingPreview,
  SourcingVariant,
} from "../api/types";
import { money, quantity } from "../format";

type Tab = "compare" | "recommend";

type Props = {
  scenarios: readonly Scenario[];
  current: Scenario;
  onClose: () => void;
  onGoToPart: (partRef: string) => void;
  /** Une variante vient d'être créée : la liste des scénarios a changé. */
  onCreated: (scenario: Scenario) => void;
  onOpenScenario: (id: string) => void;
};

export function DecisionDialog(props: Props) {
  const [tab, setTab] = useState<Tab>("compare");
  const [pair, setPair] = useState<{ a: string; b: string } | null>(null);

  return (
    <div className="overlay" onClick={props.onClose}>
      <div
        className="dialog dialog--wide"
        role="dialog"
        aria-label="Aide à la décision"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <nav className="tabs">
            <button
              className={tab === "compare" ? "tabs__on" : ""}
              onClick={() => setTab("compare")}
            >
              Comparer deux scénarios
            </button>
            <button
              className={tab === "recommend" ? "tabs__on" : ""}
              onClick={() => setTab("recommend")}
            >
              Recommander un sourcing
            </button>
          </nav>
          <button onClick={props.onClose}>Fermer</button>
        </header>

        {tab === "compare" ? (
          <ComparePane {...props} initial={pair} />
        ) : (
          <RecommendPane
            {...props}
            onCompare={(a, b) => {
              setPair({ a, b });
              setTab("compare");
            }}
          />
        )}
      </div>
    </div>
  );
}

function ComparePane({
  scenarios,
  current,
  onGoToPart,
  initial,
}: Props & { initial: { a: string; b: string } | null }) {
  const other = scenarios.find((scenario) => scenario.id !== current.id);
  const [a, setA] = useState(initial?.a ?? current.id);
  const [b, setB] = useState(initial?.b ?? other?.id ?? current.id);
  const [result, setResult] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function compare() {
    setBusy(true);
    setFailure(null);
    setResult(null);
    try {
      setResult(await api.compare(a, b));
    } catch (error) {
      setFailure(describe(error));
    } finally {
      setBusy(false);
    }
  }

  const nameOf = (id: string) =>
    scenarios.find((scenario) => scenario.id === id)?.name ?? id;

  return (
    <section className="decision">
      <div className="decision__form">
        <ScenarioSelect label="A — référence" value={a} onChange={setA} scenarios={scenarios} />
        <ScenarioSelect label="B — variante" value={b} onChange={setB} scenarios={scenarios} />
        <button className="decision__go" onClick={compare} disabled={busy || a === b}>
          {busy ? "Calcul…" : "Comparer"}
        </button>
      </div>
      {a === b && <p className="hint">Choisir deux scénarios différents.</p>}
      {failure && <p className="banner banner--danger">{failure}</p>}

      {result && (
        <>
          <dl className="decision__totals">
            <div>
              <dt>{nameOf(a)}</dt>
              <dd>{money(result.total_a)}</dd>
            </div>
            <div>
              <dt>{nameOf(b)}</dt>
              <dd>{money(result.total_b)}</dd>
            </div>
            <div>
              <dt>Écart B − A</dt>
              <dd className={deltaClass(result.cost_delta.amount)}>
                {signed(result.cost_delta.amount)}
                {money(result.cost_delta)}
              </dd>
            </div>
            <div>
              <dt>Écart CO₂</dt>
              <dd className="decision__muted">
                {result.co2_delta_kg === null
                  ? "non calculé"
                  : `${result.co2_delta_kg} kg CO₂e`}
              </dd>
            </div>
          </dl>
          <p className="provenance">
            A et B recalculés sur le même snapshot{" "}
            <code>{result.price_snapshot_id}</code> : l'écart ne vient que des
            réglages.
          </p>

          {result.top_differences.length === 0 ? (
            <p className="hint">
              Aucun écart : les deux scénarios coûtent la même chose avec ce
              snapshot.
            </p>
          ) : (
            <table className="decision__table">
              <caption>Principaux écarts, par contribution propre</caption>
              <thead>
                <tr>
                  <th>Pièce</th>
                  <th>Qté A</th>
                  <th>A</th>
                  <th>Qté B</th>
                  <th>B</th>
                  <th>B − A</th>
                </tr>
              </thead>
              <tbody>
                {result.top_differences.map((item) => (
                  <tr key={item.part_ref}>
                    <td>
                      <button className="linkish" onClick={() => onGoToPart(item.part_ref)}>
                        {item.part_ref}
                      </button>
                    </td>
                    <td>{quantity(item.cumulative_quantity_a)}</td>
                    <td>{money(item.contribution_a)}</td>
                    <td>{quantity(item.cumulative_quantity_b)}</td>
                    <td>{money(item.contribution_b)}</td>
                    <td className={deltaClass(item.delta.amount)}>
                      {signed(item.delta.amount)}
                      {money(item.delta)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}

function RecommendPane({
  current,
  onCreated,
  onOpenScenario,
  onGoToPart,
  onCompare,
}: Props & { onCompare: (a: string, b: string) => void }) {
  const [origins, setOrigins] = useState("");
  const [leadTime, setLeadTime] = useState("");
  const [preview, setPreview] = useState<SourcingPreview | null>(null);
  const [accepted, setAccepted] = useState<Set<string>>(new Set());
  const [name, setName] = useState(`${current.name} — sourcing optimisé`);
  const [variant, setVariant] = useState<SourcingVariant | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const constraints = {
    forbidden_origins: origins
      .split(/[\s,;]+/)
      .filter((origin) => origin.length > 0),
    max_lead_time_days: leadTime.trim() ? Number.parseInt(leadTime, 10) : null,
  };

  async function evaluate() {
    setBusy(true);
    setFailure(null);
    setPreview(null);
    setVariant(null);
    try {
      const result = await api.previewSourcing(current.id, constraints);
      setPreview(result);
      setAccepted(new Set(result.recommendations.map((item) => item.part_ref)));
    } catch (error) {
      setFailure(describe(error));
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!preview) return;
    setBusy(true);
    setFailure(null);
    try {
      const created = await api.createSourcingVariant(current.id, {
        ...preview.constraints,
        name: name.trim(),
        accepted_part_refs: [...accepted],
        // Le snapshot de l'aperçu : l'économie annoncée porte sur les mêmes prix.
        price_snapshot_id: preview.price_snapshot_id,
      });
      setVariant(created);
      onCreated(created.optimized_scenario);
    } catch (error) {
      setFailure(describe(error));
    } finally {
      setBusy(false);
    }
  }

  function toggle(partRef: string) {
    setAccepted((previous) => {
      const next = new Set(previous);
      if (next.has(partRef)) next.delete(partRef);
      else next.add(partRef);
      return next;
    });
  }

  return (
    <section className="decision">
      <p className="hint decision__lead">
        Pour chaque pièce achetée de <strong>{current.name}</strong>, l'option
        fournisseur × usine la moins chère parmi celles autorisées. Rien n'est
        modifié : une variante est créée avec les lignes cochées.
      </p>
      <div className="decision__form">
        <label>
          Provenances interdites
          <input
            placeholder="ex. RU, TR"
            value={origins}
            onChange={(event) => setOrigins(event.target.value)}
          />
        </label>
        <label>
          Délai maximal (jours)
          <input
            inputMode="numeric"
            placeholder="aucun"
            value={leadTime}
            onChange={(event) => setLeadTime(event.target.value)}
          />
        </label>
        <button className="decision__go" onClick={evaluate} disabled={busy}>
          {busy && !preview ? "Évaluation…" : "Évaluer"}
        </button>
      </div>
      {failure && <p className="banner banner--danger">{failure}</p>}

      {preview && preview.unresolved.length > 0 && (
        <div className="banner banner--danger">
          <strong>
            {preview.unresolved.length} pièce(s) violent une contrainte sans
            option autorisée
          </strong>{" "}
          — elles resteront telles quelles dans la variante :
          <ul className="decision__unresolved">
            {preview.unresolved.map((item) => (
              <li key={item.part_ref}>
                <button className="linkish" onClick={() => onGoToPart(item.part_ref)}>
                  {item.part_ref}
                </button>{" "}
                ({item.current.supplier_id} / {item.current.plant_id},{" "}
                {item.current.origin_country})
              </li>
            ))}
          </ul>
        </div>
      )}

      {preview && preview.recommendations.length === 0 && (
        <p className="hint">
          Aucune option moins chère ni imposée : le sourcing actuel est déjà le
          meilleur sous ces contraintes.
        </p>
      )}

      {preview && preview.recommendations.length > 0 && !variant && (
        <>
          <table className="decision__table">
            <caption>
              {preview.recommendations.length} recommandation(s) — snapshot{" "}
              <code>{preview.price_snapshot_id}</code>
            </caption>
            <thead>
              <tr>
                <th />
                <th>Pièce</th>
                <th>Actuel</th>
                <th>Proposé</th>
                <th>Qté</th>
                <th>Économie estimée</th>
              </tr>
            </thead>
            <tbody>
              {preview.recommendations.map((item) => (
                <tr key={item.part_ref}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Appliquer ${item.part_ref}`}
                      checked={accepted.has(item.part_ref)}
                      onChange={() => toggle(item.part_ref)}
                    />
                  </td>
                  <td>
                    <button className="linkish" onClick={() => onGoToPart(item.part_ref)}>
                      {item.part_ref}
                    </button>
                    {item.required_by_constraint && (
                      <span className="chip chip--warn" title="L'option actuelle viole une contrainte">
                        imposé
                      </span>
                    )}
                  </td>
                  <td>
                    {item.current.plant_id} ({item.current.origin_country})
                    <br />
                    {money(item.current.unit_price)}
                  </td>
                  <td>
                    {item.recommended.plant_id} ({item.recommended.origin_country},{" "}
                    {item.recommended.lead_time_days} j)
                    <br />
                    {money(item.recommended.unit_price)}
                  </td>
                  <td>{quantity(item.affected_quantity)}</td>
                  <td className={deltaClass(negated(item.estimated_saving.amount))}>
                    {money(item.estimated_saving)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="decision__form">
            <label className="decision__name">
              Nom de la variante
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <button
              className="decision__go"
              onClick={create}
              disabled={busy || !name.trim()}
            >
              {busy ? "Création…" : `Créer la variante (${accepted.size} ligne(s))`}
            </button>
          </div>
        </>
      )}

      {variant && (
        <div className="banner banner--ok">
          <p>
            Variante <strong>{variant.optimized_scenario.name}</strong> créée —
            économie sur le véhicule : <strong>{money(variant.savings)}</strong>.
            Le scénario d'origine n'a pas été modifié.
          </p>
          <div className="decision__form">
            <button onClick={() => onCompare(current.id, variant.optimized_scenario.id)}>
              Comparer à {current.name}
            </button>
            <button onClick={() => onOpenScenario(variant.optimized_scenario.id)}>
              Ouvrir la variante
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function ScenarioSelect({
  label,
  value,
  onChange,
  scenarios,
}: {
  label: string;
  value: string;
  onChange: (id: string) => void;
  scenarios: readonly Scenario[];
}) {
  return (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {scenarios.map((scenario) => (
          <option key={scenario.id} value={scenario.id}>
            {scenario.name}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Le signe se lit sur la chaîne telle que l'API l'a écrite : aucune
 * comparaison numérique, donc aucune arithmétique sur un montant.
 */
function deltaClass(amount: string): string {
  if (amount.startsWith("-")) return "delta delta--down";
  return /[1-9]/.test(amount) ? "delta delta--up" : "delta";
}

function signed(amount: string): string {
  return !amount.startsWith("-") && /[1-9]/.test(amount) ? "+" : "";
}

/** Une économie positive est une baisse de coût : même couleur qu'un delta négatif. */
function negated(amount: string): string {
  if (!/[1-9]/.test(amount)) return amount;
  return amount.startsWith("-") ? amount.slice(1) : `-${amount}`;
}

function describe(error: unknown): string {
  if (error instanceof ApiFailure) return `${error.code} — ${error.message}`;
  return error instanceof Error ? error.message : "erreur inconnue";
}
