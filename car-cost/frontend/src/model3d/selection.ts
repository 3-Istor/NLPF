/**
 * Le lien entre les objets du modèle et les pièces de la nomenclature. Aucun
 * chiffre : l'ensemble coloré est celui que l'API sert (`body-changes`).
 */

import type { PartChange } from "../api/types";

type Picked = { id: string; ref: string | null };

/** `GLTFLoader` copie `node.extras` dans `userData` ; sans `carcost.ref`, c'est du décor. */
export function refOf(userData: unknown): string | null {
  const ref = (userData as { carcost?: { ref?: unknown } } | null)?.carcost?.ref;
  return typeof ref === "string" ? ref : null;
}

export function refOfPath(path: string | null): string | null {
  return path === null ? null : path.slice(path.lastIndexOf("/") + 1);
}

/** Tous les emplacements de la pièce : une même référence peut être montée plusieurs fois. */
export function highlighted(objects: Picked[], selectedRef: string | null): Set<string> {
  return new Set(objects.filter((o) => o.ref !== null && o.ref === selectedRef).map((o) => o.id));
}

export function colored(objects: Picked[], changes: PartChange[]): Set<string> {
  const refs = new Set(changes.map((c) => c.part_ref));
  return new Set(objects.filter((o) => o.ref !== null && refs.has(o.ref)).map((o) => o.id));
}
