/**
 * La recherche : le champ, le compteur, et le parcours des résultats.
 *
 * Le compteur parle en **occurrences** (une pièce montée à trois endroits
 * compte trois fois), parce que c'est ce que l'on parcourt : chaque résultat
 * est un chemin de l'arbre. Les totaux viennent du serveur ; seuls les chemins
 * servis sont parcourables, et le compteur le dit quand ils sont moins
 * nombreux que les occurrences.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { api, ApiFailure } from "../api/client";
import type { SearchResponse } from "../api/types";

/** Chemins servis par pièce : la valeur par défaut du serveur, demandée explicitement. */
const MAX_PATHS = 50;

/** La recherche suit la frappe, après ce délai de calme. */
const TYPING_DELAY_MS = 250;
/** En dessous, presque tout correspond : on attend une lettre de plus. */
const MIN_LENGTH = 2;

type Props = {
  version: string;
  /** Aller à un chemin : déplier ses ancêtres, le sélectionner, le montrer. */
  onNavigate: (path: string) => void | Promise<void>;
  /** La requête à surligner ; `""` quand il n'y en a plus. */
  onQueryChange?: (query: string) => void;
};

type Result = {
  query: string;
  paths: readonly string[];
  totalParts: number;
  totalOccurrences: number;
};

function toResult(query: string, response: SearchResponse): Result {
  return {
    query,
    paths: response.items.flatMap((hit) => hit.paths),
    totalParts: response.total_parts,
    totalOccurrences: response.total_occurrences,
  };
}

function counter(result: Result, index: number): string {
  if (result.totalOccurrences === 0) return "0 résultat";
  const position = result.paths.length > 0 ? index + 1 : 0;
  const text = `${position} / ${result.totalOccurrences} résultats (${result.totalParts} pièces)`;
  return result.paths.length < result.totalOccurrences
    ? `${text}, ${result.paths.length} parcourables`
    : text;
}

function describe(error: unknown): string {
  if (error instanceof ApiFailure) return `${error.code} : ${error.message}`;
  return error instanceof Error ? error.message : "erreur inconnue";
}

export function SearchBar({ version, onNavigate, onQueryChange }: Props) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [index, setIndex] = useState(0);
  const [failure, setFailure] = useState<string | null>(null);
  // Chaque requête porte un numéro : une réponse plus ancienne que la
  // dernière demandée arrive trop tard et ne doit rien écraser.
  const latest = useRef(0);
  const typing = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancelTyping = () => {
    if (typing.current !== null) clearTimeout(typing.current);
    typing.current = null;
  };
  useEffect(() => cancelTyping, []);

  const step = useCallback(
    (delta: 1 | -1) => {
      if (!result || result.paths.length === 0) return;
      const count = result.paths.length;
      const next = (index + delta + count) % count;
      setIndex(next);
      void onNavigate(result.paths[next]);
    },
    [result, index, onNavigate],
  );

  async function run(query: string) {
    const ticket = ++latest.current;
    setFailure(null);
    try {
      const response = await api.search(version, query, MAX_PATHS);
      if (ticket !== latest.current) return;
      const fresh = toResult(query, response);
      setResult(fresh);
      setIndex(0);
      onQueryChange?.(query);
      if (fresh.paths.length > 0) void onNavigate(fresh.paths[0]);
    } catch (error) {
      if (ticket !== latest.current) return;
      setResult(null);
      onQueryChange?.("");
      setFailure(describe(error));
    }
  }

  /** Entrée : une nouvelle requête cherche, la même passe au suivant. */
  function submit(backwards: boolean) {
    const query = text.trim();
    if (!query) return;
    cancelTyping();
    if (result && result.query === query) step(backwards ? -1 : 1);
    else void run(query);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    submit(event.shiftKey);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    submit(false);
  }

  /** Chaque frappe relance la recherche, une fois la saisie calmée. */
  function onChange(value: string) {
    setText(value);
    cancelTyping();
    const query = value.trim();
    if (query === "") {
      latest.current += 1;
      setResult(null);
      setFailure(null);
      onQueryChange?.("");
      return;
    }
    if (query.length < MIN_LENGTH) return;
    typing.current = setTimeout(() => {
      typing.current = null;
      void run(query);
    }, TYPING_DELAY_MS);
  }

  // F3 et Maj+F3 sur toute la fenêtre, comme la recherche d'un navigateur.
  useEffect(() => {
    if (!result) return;
    const onWindowKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "F3") return;
      event.preventDefault();
      step(event.shiftKey ? -1 : 1);
    };
    window.addEventListener("keydown", onWindowKey);
    return () => window.removeEventListener("keydown", onWindowKey);
  }, [result, step]);

  const browsable = result !== null && result.paths.length > 0;

  return (
    <form className="search" role="search" onSubmit={onSubmit}>
      <input
        type="search"
        aria-label="Chercher une référence ou un libellé"
        placeholder="Chercher une référence ou un libellé…"
        value={text}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <button
        type="button"
        onClick={() => step(-1)}
        disabled={!browsable}
        aria-label="Résultat précédent"
        title="Résultat précédent (Maj+Entrée, Maj+F3)"
      >
        ↑
      </button>
      <button
        type="button"
        onClick={() => step(1)}
        disabled={!browsable}
        aria-label="Résultat suivant"
        title="Résultat suivant (Entrée, F3)"
      >
        ↓
      </button>
      <span className="search__count" role="status">
        {result ? counter(result, index) : ""}
      </span>
      {failure && (
        <span className="search__error" role="alert">
          {failure}
        </span>
      )}
    </form>
  );
}
