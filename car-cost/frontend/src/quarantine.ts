/**
 * Le journal de quarantaine, mis à portée de chaque ligne de l'arbre.
 *
 * Une ligne en quarantaine doit dire ce qui a été refusé, pourquoi, et ce qui
 * a été retenu à la place — pas seulement renvoyer au journal (cadrage, mode de
 * panne P2). Le journal est lu une fois par calcul et partagé ici plutôt que
 * redemandé ligne à ligne.
 *
 * Ce module associe une référence à son entrée ; il ne calcule rien.
 */

import { createContext } from "react";
import type { QuarantineEntry, QuarantineJournal } from "./api/types";
import { money } from "./format";

export const Refusals = createContext<ReadonlyMap<string, QuarantineEntry>>(
  new Map(),
);

export function byPart(
  journal: QuarantineJournal | null,
): ReadonlyMap<string, QuarantineEntry> {
  return new Map(journal?.items.map((entry) => [entry.part_ref, entry]) ?? []);
}

/** Ce qui a été refusé et pourquoi, dans les termes du journal. */
export function refusal(entry: QuarantineEntry): string {
  return `« ${entry.rejected_value} » refusé : ${entry.reason}`;
}

/**
 * La phrase complète, pour l'infobulle d'une ligne.
 *
 * Ce qui est retenu est un prix de **référence** : fournisseur et usine
 * s'appliquent ensuite (ADR-0010), et la ligne affiche un autre montant. Sans
 * le mot, les deux chiffres ont l'air de se contredire.
 */
export function describeRefusal(entry: QuarantineEntry): string {
  if (!entry.replacement) return `${refusal(entry)}. Aucun prix retenu.`;
  const source = entry.replacement_from_snapshot
    ? ` (snapshot ${entry.replacement_from_snapshot})`
    : "";
  return `${refusal(entry)}. Référence retenue : ${money(entry.replacement)}${source}.`;
}
