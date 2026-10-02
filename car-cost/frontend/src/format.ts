/**
 * Le seul endroit du front qui arrondit.
 *
 * Arrondir est un acte d'affichage (ADR-0011). Additionner, multiplier ou
 * convertir des montants reste interdit ici : ces opérations appartiennent à
 * l'API, et deux vérités qui coexistent finissent par diverger.
 */

import type { Co2, Money } from "./api/types";

const CURRENCIES: Record<string, string> = {
  EUR: "€",
  USD: "$",
  RUB: "₽",
};

/** Formate un montant pour l'œil. Ne le transforme pas. */
export function money(value: Money | null | undefined): string {
  if (!value) return "—";
  const rounded = Number.parseFloat(value.amount).toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${rounded} ${CURRENCIES[value.currency] ?? value.currency}`;
}

/**
 * Formate une masse de CO₂e. Accepte la chaîne nue de `co2_delta_kg` comme
 * l'objet `{ kg_co2e }` des calculs. `null` : inconnu, jamais zéro.
 */
export function co2(value: Co2 | string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const kg = typeof value === "string" ? value : value.kg_co2e;
  const rounded = Number.parseFloat(kg).toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${rounded} kg CO₂e`;
}

/** Une quantité garde ses décimales utiles, et rien de plus. */
export function quantity(value: string | undefined, unit?: string): string {
  if (value === undefined) return "—";
  const asNumber = Number.parseFloat(value);
  const text = Number.isInteger(asNumber)
    ? String(asNumber)
    : asNumber.toLocaleString("fr-FR", { maximumFractionDigits: 3 });
  return unit ? `${text} ${unit}` : text;
}

export function percent(value: string): string {
  return `${value.replace(".", ",")} %`;
}

/** L'âge d'un snapshot, en clair : c'est ce que l'utilisateur doit juger. */
export function age(seconds: number): string {
  if (seconds < 60) return "à l'instant";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `il y a ${hours} h`;
  return `il y a ${Math.floor(hours / 24)} j`;
}
