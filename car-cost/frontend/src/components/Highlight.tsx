import { segments } from "../tree/fold";

/** Texte avec les correspondances en `<mark>`, rendu en nœuds React (jamais en HTML). */
export function Highlight({ text, query }: { text: string; query: string }) {
  return (
    <>
      {segments(text, query).map((s, i) =>
        s.match ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>,
      )}
    </>
  );
}
