/**
 * Une ligne de l'arbre, et ce qu'elle déplie.
 *
 * Le dépliage demande les **enfants directs** au serveur, au moment où on
 * l'ouvre. L'arbre entier n'est jamais monté en mémoire : sur 474 pièces, le
 * charger d'un coup rendrait aussi le recalcul local tentant, puis inévitable
 * (ADR-0009).
 */

import { useContext } from "react";
import type { Scenario, TreeLine } from "../api/types";
import { money, quantity } from "../format";
import { describeRefusal, Refusals } from "../quarantine";
import type { TreeState } from "../tree/useTreeState";
import { NodePanel } from "./NodePanel";
import { rowId } from "./Tree";

type Props = {
  line: TreeLine;
  depth: number;
  state: TreeState;
  version: string;
  scenario: Scenario | null;
  onParameterChanged: () => void;
  onShowWhereUsed: (partRef: string) => void;
};

/**
 * Un paramètre du scénario vise-t-il cette ligne ? Une recherche, pas un
 * calcul : la portée pièce vise toutes les occurrences de la référence, la
 * portée chemin cette occurrence seulement. La ligne est marquée dès la
 * saisie, sans attendre le recalcul.
 */
function isTargeted(line: TreeLine, scenario: Scenario | null): boolean {
  return (scenario?.parameters ?? []).some((parameter) =>
    parameter.scope === "part"
      ? parameter.part_ref === line.part_ref
      : parameter.path === line.path,
  );
}

export function TreeNode({
  line,
  depth,
  state,
  version,
  scenario,
  onParameterChanged,
  onShowWhereUsed,
}: Props) {
  // Un nœud n'est rendu que si son parent est déplié : un sous-niveau resté
  // déplié sous un parent replié n'est donc jamais affiché.
  const open = state.isExpanded(line.path);
  const entry = open ? state.childrenOf(line.path) : undefined;
  // Le panneau suit la sélection, pas le dépliage : une pièce achetée est une
  // feuille, et c'est précisément elle qui porte fournisseur, usine et prix.
  const selected = state.selected === line.path;

  const modified = line.is_modified === true || isTargeted(line, scenario);
  const inPath = line.has_modified_descendant === true;
  const refused = useContext(Refusals).get(line.part_ref);

  return (
    <li className="node">
      <div
        id={rowId(line.path)}
        aria-selected={selected}
        className={`row${modified ? " row--modified" : ""}${
          inPath ? " row--in-modified-path" : ""
        }${selected ? " row--selected" : ""}`}
        style={{ paddingLeft: `${depth * 18 + 8}px` }}
      >
        <button
          className="chevron"
          onClick={() => state.toggle(line.path)}
          disabled={!line.has_children}
          aria-expanded={open}
          aria-label={open ? "Replier" : "Déplier"}
        >
          {line.has_children ? (open ? "▾" : "▸") : "·"}
        </button>

        <button
          className="label"
          onClick={() => state.select(line.path)}
          title="Régler cette pièce"
        >
          {line.label}
        </button>
        <code className="ref">{line.part_ref}</code>

        <span className="qty">
          × {quantity(line.edge_quantity)} {line.unit}
        </span>

        {line.occurrence_count > 1 && (
          <button
            className="badge"
            onClick={() => onShowWhereUsed(line.part_ref)}
            title="Voir tous les emplacements de montage"
          >
            utilisée à {line.occurrence_count} endroits
          </button>
        )}

        {modified && <span className="mark" title="Paramètre modifié">●</span>}
        {!modified && inPath && (
          <span className="mark mark--faint" title="Contient une modification">
            ○
          </span>
        )}

        {line.price_status === "MISSING" && (
          <span className="chip chip--danger">prix manquant</span>
        )}
        {line.price_status === "FALLBACK" && (
          <span
            className="chip chip--warn"
            title="Absent de la réponse de l'API : le dernier prix connu a été retenu."
          >
            prix de repli
          </span>
        )}
        {line.price_status === "QUARANTINED" && (
          <span
            className="chip chip--warn"
            title={
              refused
                ? describeRefusal(refused)
                : "Valeur refusée par le contrôle : le dernier prix sain a été retenu."
            }
          >
            prix en quarantaine
          </span>
        )}

        <span className="cost" title="Coût unitaire">
          {money(line.unit_cost)}
        </span>
        <span className="cost cost--strong" title="Ce que pèse cette occurrence">
          {money(line.rolled_up_contribution)}
        </span>
      </div>

      {selected && scenario && (
        <NodePanel
          line={line}
          version={version}
          scenarioId={scenario.id}
          depth={depth}
          onChanged={onParameterChanged}
        />
      )}

      {open && (
        <>
          {(entry === undefined || entry.status === "loading") && (
            <p className="hint">chargement…</p>
          )}
          {entry?.status === "error" && (
            <p className="hint hint--danger">
              {entry.message}{" "}
              <button onClick={() => state.retry(line.path)}>Réessayer</button>
            </p>
          )}
          {entry?.status === "ready" && entry.page.items.length > 0 && (
            <ul className="children">
              {entry.page.items.map((child) => (
                <TreeNode
                  key={child.path}
                  line={child}
                  depth={depth + 1}
                  state={state}
                  version={version}
                  scenario={scenario}
                  onParameterChanged={onParameterChanged}
                  onShowWhereUsed={onShowWhereUsed}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </li>
  );
}
