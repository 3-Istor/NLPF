/**
 * Pliage du texte de recherche : sans accents, sans casse.
 *
 * Même règle que le serveur (`backend/src/carcost/domain/text_folding.py`),
 * vérifiée sur la même table `backend/tests/fold_cases.json`. Seul écart connu,
 * cosmétique : « ß » (`casefold` Python donne « ss », `toLowerCase` le garde).
 */

export interface Segment {
  text: string;
  match: boolean;
}

export function fold(text: string): string {
  return text.normalize("NFKD").replace(/\p{Mn}/gu, "").toLowerCase();
}

/**
 * Découpe le texte d'origine en segments, ceux qui correspondent à la requête
 * étant marqués. Le pliage se fait caractère par caractère : un caractère
 * d'origine peut donner plusieurs caractères pliés (« ﬁ » donne « fi »), et
 * chacun renvoie à l'intervalle d'origine dont il vient.
 */
export function segments(text: string, query: string): Segment[] {
  const needle = fold(query);
  if (needle === "") return [{ text, match: false }];

  let folded = "";
  const starts: number[] = [];
  const ends: number[] = [];
  let offset = 0;
  for (const char of text) {
    const piece = fold(char);
    for (let i = 0; i < piece.length; i++) {
      starts.push(offset);
      ends.push(offset + char.length);
    }
    folded += piece;
    offset += char.length;
  }

  const result: Segment[] = [];
  let cursor = 0;
  let from = 0;
  for (;;) {
    const hit = folded.indexOf(needle, from);
    if (hit === -1) break;
    const last = hit + needle.length - 1;
    const begin = starts[hit];
    const end = ends[last];
    from = last + 1;
    if (begin < cursor) continue; // chevauche un segment déjà pris
    if (begin > cursor) result.push({ text: text.slice(cursor, begin), match: false });
    result.push({ text: text.slice(begin, end), match: true });
    cursor = end;
  }
  if (cursor < text.length) result.push({ text: text.slice(cursor), match: false });
  return result.length > 0 ? result : [{ text, match: false }];
}
