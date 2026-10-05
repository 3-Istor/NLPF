/**
 * Une ligne de l'arbre, et ce qu'elle déplie.
 *
 * Le dépliage demande les **enfants directs** au serveur, au moment où on
 * l'ouvre. L'arbre entier n'est jamais monté en mémoire : sur 474 pièces, le
 * charger d'un coup rendrait aussi le recalcul local tentant, puis inévitable
 * (ADR-0009).
 */

import { useContext } from "react";
import type { CalculationSnapshot, Scenario, TreeLine } from "../api/types";
import { money, percent, quantity } from "../format";
import { describeRefusal, Refusals } from "../quarantine";
import type { TreeState } from "../tree/useTreeState";
import { FrozenSettings } from "./FrozenSettings";
import { Highlight } from "./Highlight";
import { NodePanel } from "./NodePanel";
import { rowId } from "./rowId";

type Props = {
  line: TreeLine;
  depth: number;
  state: TreeState;
  version: string;
  scenario: Scenario | null;
  /**
   * Le snapshot de calcul ouvert : la ligne sélectionnée montre ses réglages
   * copiés, en lecture seule, au lieu du panneau de saisie.
   */
  frozen?: CalculationSnapshot | null;
  /** La seule ligne atteignable par Tab (roving tabindex). */
  tabStop: string;
  /** La ligne atteinte au clavier dont le panneau attend Entrée. */
  browsed: string | null;
  onOpenPanel: () => void;
  /** Sélectionne la ligne sans ouvrir son panneau : on la parcourt. */
  onBrowse: (path: string) => void;
  onParameterChanged: () => void;
  onShowWhereUsed: (partRef: string) => void;
  /** La recherche courante : ses correspondances sont surlignées. */
  query?: string;
};

/** L'id DOM de la liste des enfants d'une ligne, que la ligne possède (aria-owns). */
const groupId = (path: string) => `group-${path}`;

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
  frozen = null,
  tabStop,
  browsed,
  onOpenPanel,
  onBrowse,
  onParameterChanged,
  onShowWhereUsed,
  query = "",
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
  // L'ancienne page reste affichée le temps que la nouvelle arrive : on le
  // dit, sans toucher aux montants.
  const refreshing =
    entry?.status === "ready" && entry.calculationId !== state.calculationId;
  const refused = useContext(Refusals).get(line.part_ref);

  return (
    <li className="node" role="none">
      <div
        id={rowId(line.path)}
        role="treeitem"
        aria-level={depth + 1}
        aria-expanded={line.has_children ? open : undefined}
        aria-owns={open ? groupId(line.path) : undefined}
        aria-selected={selected}
        tabIndex={line.path === tabStop ? 0 : -1}
        className={`row row-grid${modified ? " row--modified" : ""}${
          inPath ? " row--in-modified-path" : ""
        }${selected ? " row--selected" : ""}${depth === 1 ? " row--level1" : ""}`}
      >
        <div className="cell cell--label">
          {Array.from({ length: depth }, (_, level) => (
            <span key={level} className="guide" aria-hidden="true" />
          ))}
          <button
            className="chevron"
            onClick={() => state.toggle(line.path)}
            tabIndex={-1}
            disabled={!line.has_children}
            aria-expanded={open}
            aria-label={open ? "Replier" : "Déplier"}
          >
            {line.has_children ? (open ? "▾" : "▸") : "·"}
          </button>
          {/* Le libellé fait ce qu'on attend de lui : un ensemble se déplie, une
              feuille (rien à déplier) ouvre son panneau. Déplier n'ouvre pas le
              panneau d'un ensemble : suivre un chemin en ouvrirait un à chaque
              niveau. */}
          <button
            className="label"
            onClick={() => {
              if (line.has_children) {
                onBrowse(line.path);
                state.toggle(line.path);
              } else {
                state.select(line.path);
                onOpenPanel();
              }
            }}
            tabIndex={-1}
            title={line.has_children ? (open ? "Replier" : "Déplier") : undefined}
          >
            <Highlight text={line.label} query={query} />
          </button>
          <button
            className="row-action"
            onClick={() => {
              state.select(line.path);
              onOpenPanel();
            }}
            tabIndex={-1}
            aria-label={frozen ? "Voir les réglages figés" : "Régler cette pièce"}
            title={frozen ? "Voir les réglages figés" : "Régler cette pièce"}
          >
            {frozen ? "réglages" : "régler"}
          </button>
        </div>

        <code className="cell ref" title={line.part_ref}>
          <Highlight text={line.part_ref} query={query} />
        </code>

        <span className="cell num qty">
          × {quantity(line.edge_quantity)} {line.unit}
          {hasAfterSales(line.after_sales_quantity) && (
            <span
              className="qty__sav"
              title="Pièces de rechange livrées avec le véhicule, comptées si le SAV est activé"
            >
              {" "}+ {quantity(line.after_sales_quantity)} SAV
            </span>
          )}
        </span>
        <span className="cell num cell--path-qty">{quantity(line.quantity_on_path)}</span>

        <span className="cell num cost" title="Coût unitaire">
          {money(line.unit_cost)}
        </span>
        <span className="cell num cost cost--strong" title="Ce que pèse cette occurrence">
          {money(line.rolled_up_contribution)}
        </span>

        <span className="cell num cell--share">
          {line.share_of_total_pct ? (
            <>
              <span>{percent(line.share_of_total_pct)}</span>
              <span className="bar" aria-hidden="true">
                <i style={{ width: `${line.share_of_total_pct}%` }} />
              </span>
            </>
          ) : (
            "—"
          )}
        </span>

        <span className="cell cell--status">
          {modified && <span className="mark" title="Paramètre modifié">●</span>}
          {!modified && inPath && (
            <span className="mark mark--faint" title="Contient une modification">
              ○
            </span>
          )}
          {refreshing && <span className="chip">mise à jour…</span>}

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
          {line.occurrence_count > 1 && (
            <button
              className="badge"
              onClick={() => onShowWhereUsed(line.part_ref)}
              title="Voir tous les emplacements de montage"
            >
              utilisée à {line.occurrence_count} endroits
            </button>
          )}
        </span>
      </div>

      {selected && frozen && browsed !== line.path && (
        <FrozenSettings line={line} snapshot={frozen} version={version} depth={depth} />
      )}

      {selected && !frozen && scenario && browsed !== line.path && (
        <NodePanel
          line={line}
          version={version}
          scenario={scenario}
          depth={depth}
          onChanged={onParameterChanged}
        />
      )}

      {open && (
        <ul className="children" role="group" id={groupId(line.path)}>
          {(entry === undefined || entry.status === "loading") && (
            <li className="node-status" role="status">
              chargement…
            </li>
          )}
          {entry?.status === "error" && (
            <li className="node-status node-status--danger">
              {entry.message}{" "}
              <button onClick={() => state.retry(line.path)}>réessayer</button>
            </li>
          )}
          {entry?.status === "ready" && (
            <>
              {entry.page.items.map((child) => (
                <TreeNode
                  key={child.path}
                  line={child}
                  depth={depth + 1}
                  state={state}
                  version={version}
                  scenario={scenario}
                  frozen={frozen}
                  tabStop={tabStop}
                  browsed={browsed}
                  onOpenPanel={onOpenPanel}
                  onBrowse={onBrowse}
                  onParameterChanged={onParameterChanged}
                  onShowWhereUsed={onShowWhereUsed}
                  query={query}
                />
              ))}
              {entry.page.items.length === 0 && (
                <li className="node-status">aucun enfant</li>
              )}
              {entry.page.total > entry.page.items.length &&
                entry.page.items.length > 0 && (
                  <li className="node-status">
                    {entry.page.items.length} enfants sur {entry.page.total}
                  </li>
                )}
            </>
          )}
        </ul>
      )}
    </li>
  );
}

/** Une quantité SAV nulle ou absente ne s'affiche pas : « + 0 SAV » serait du bruit. */
function hasAfterSales(value: string | undefined): boolean {
  return value !== undefined && Number.parseFloat(value) !== 0;
}
