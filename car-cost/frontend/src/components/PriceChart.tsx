/**
 * La variation du prix d'une pièce sur l'année de marché simulée.
 *
 * Les montants viennent de l'API tels quels ; ce composant ne calcule que des
 * positions à l'écran. La courbe est datée en temps simulé (une année dure
 * 40 minutes réelles) : les snapshots, datés en temps réel, ne se placent pas
 * sur cet axe et sont listés à côté.
 *
 * SVG à la main plutôt qu'une bibliothèque de graphes : une courbe, un repère
 * et un marqueur ne justifient pas une dépendance.
 */

import { useEffect, useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { PriceHistoryResponse } from "../api/types";
import { money } from "../format";

const WIDTH = 640;
const HEIGHT = 220;
const PAD = { top: 12, right: 12, bottom: 26, left: 64 };
const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
/** Le marché simulé avance d'environ 9 jours par minute : on suit. */
const REFRESH_MS = 5000;

type Props = { version: string; partRef: string; currency?: string };

export function PriceChart({ version, partRef, currency = "EUR" }: Props) {
  const [history, setHistory] = useState<PriceHistoryResponse | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setHistory(null);
    setFailure(null);
    const load = () =>
      api
        .priceHistory(version, partRef, currency)
        .then((body) => {
          if (!alive) return;
          setHistory(body);
          setFailure(null);
        })
        .catch((error) => alive && setFailure(describe(error)));
    void load();
    const timer = window.setInterval(() => void load(), REFRESH_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [version, partRef, currency]);

  if (failure && !history) {
    return (
      <p className="banner banner--danger" role="alert">
        Historique de prix indisponible : {failure}
      </p>
    );
  }
  if (!history) return <p className="hint">chargement de l'historique…</p>;

  const values = history.points.map((point) => Number.parseFloat(point.price));
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || Math.abs(high) || 1;
  const x = (day: number) =>
    PAD.left + (day / (values.length - 1)) * (WIDTH - PAD.left - PAD.right);
  const y = (value: number) =>
    PAD.top + (1 - (value - (low - span * 0.05)) / (span * 1.1)) * (HEIGHT - PAD.top - PAD.bottom);
  const line = values.map((value, day) => `${day ? "L" : "M"}${x(day).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
  const nowDay = dayOf(history.points[0].date, history.now.at, values.length);
  const nowValue = Number.parseFloat(history.now.price);
  const reference = Number.parseFloat(history.reference);
  const lowIndex = values.indexOf(low);
  const highIndex = values.indexOf(high);
  const amount = (raw: string) => money({ amount: raw, currency: history.currency });

  return (
    <figure className="price-chart">
      <figcaption>
        <strong>{history.label}</strong> <code>{history.part_ref}</code>
        <span className="price-chart__now">
          maintenant : {amount(history.now.price)} / {history.unit}
        </span>
        <span className="price-chart__meta">
          profil {history.profile ?? "—"}
          {history.origin_currency && ` · fournisseur facturant en ${history.origin_currency}`}
          {" · données synthétiques"}
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={
          `Prix de ${history.label} sur l'année simulée : de ${amount(history.points[lowIndex].price)} ` +
          `à ${amount(history.points[highIndex].price)}, ${amount(history.now.price)} maintenant`
        }
      >
        {MONTHS.map((month, index) => {
          const position = x((index * values.length) / 12);
          return (
            <g key={month}>
              <line x1={position} x2={position} y1={PAD.top} y2={HEIGHT - PAD.bottom} className="price-chart__grid" />
              <text x={position + 2} y={HEIGHT - 8} className="price-chart__axis">{month}</text>
            </g>
          );
        })}
        <line
          x1={PAD.left} x2={WIDTH - PAD.right} y1={y(reference)} y2={y(reference)}
          className="price-chart__reference"
        />
        <text x={4} y={y(reference) + 4} className="price-chart__axis">référence</text>
        <text x={4} y={y(high) + 4} className="price-chart__axis">{compact(high)}</text>
        <text x={4} y={y(low) + 4} className="price-chart__axis">{compact(low)}</text>
        <path d={line} className="price-chart__line" />
        <line
          x1={x(nowDay)} x2={x(nowDay)} y1={PAD.top} y2={HEIGHT - PAD.bottom}
          className="price-chart__today"
        />
        <circle cx={x(nowDay)} cy={y(nowValue)} r={4} className="price-chart__dot" />
      </svg>
      <dl className="price-chart__facts">
        <dt>Référence</dt><dd>{amount(history.reference)}</dd>
        <dt>Plus bas de l'année</dt><dd>{amount(history.points[lowIndex].price)} ({history.points[lowIndex].date})</dd>
        <dt>Plus haut de l'année</dt><dd>{amount(history.points[highIndex].price)} ({history.points[highIndex].date})</dd>
        <dt>Date simulée</dt><dd>{history.now.at.slice(0, 10)}</dd>
      </dl>
      <div className="price-chart__frozen">
        <h4>Prix figés (snapshots)</h4>
        {history.snapshots.length === 0 ? (
          <p className="hint">Aucun snapshot ne cote cette pièce.</p>
        ) : (
          <ul>
            {history.snapshots.map((snapshot) => (
              <li key={snapshot.id}>
                {amount(snapshot.price)} — <code>{snapshot.id}</code>,{" "}
                {new Date(snapshot.taken_at).toLocaleString("fr-FR")}
                {snapshot.origin === "FALLBACK" && " (repli sur le prix précédent)"}
              </li>
            ))}
          </ul>
        )}
      </div>
      {failure && <p className="hint">Dernière actualisation échouée : {failure}</p>}
    </figure>
  );
}

/** Le jour simulé de `at`, compté depuis le premier point de la courbe. */
function dayOf(first: string, at: string, days: number): number {
  const elapsed = (Date.parse(at) - Date.parse(`${first}T00:00:00Z`)) / 86_400_000;
  return Math.min(Math.max(elapsed, 0), days - 1);
}

/** Libellé d'axe : quelques chiffres significatifs, pas un montant. */
function compact(value: number): string {
  return value.toLocaleString("fr-FR", { maximumSignificantDigits: 4 });
}

function describe(error: unknown): string {
  if (error instanceof ApiFailure) return `${error.code} — ${error.message}`;
  return error instanceof Error ? error.message : "erreur inconnue";
}
