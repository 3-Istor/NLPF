/**
 * Une ligne de l'arbre, et ce qu'elle déplie.
 *
 * Le dépliage demande les **enfants directs** au serveur, au moment où on
 * l'ouvre. L'arbre entier n'est jamais monté en mémoire : sur 474 pièces, le
 * charger d'un coup rendrait aussi le recalcul local tentant, puis inévitable
 * (ADR-0009).
 */

import { useContext, useState } from "react";
import { api } from "../api/client";
import type { Page, TreeLine } from "../api/types";
import { money, quantity } from "../format";
import { describeRefusal, Refusals } from "../quarantine";
import { NodePanel } from "./NodePanel";

type Props = {
  line: TreeLine;
  version: string;
  scenarioId: string | null;
  calculationId: string | null;
  depth: number;
  expandTo?: string[];
  onParameterChanged: () => void;
  onShowWhereUsed: (partRef: string) => void;
};

export function TreeNode({
  line,
  version,
  scenarioId,
  calculationId,
  depth,
  expandTo,
  onParameterChanged,
  onShowWhereUsed,
}: Props) {
  const [children, setChildren] = useState<TreeLine[] | null>(null);
  const [open, setOpen] = useState(false);
  // Le panneau s'ouvre indépendamment des enfants : une pièce achetée est une
  // feuille, et c'est précisément elle qui porte fournisseur, usine et prix.
  // Le lier au dépliage rendrait inaccessible le réglage le plus utile.
  const [panelOpen, setPanelOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const shouldFollow = expandTo?.[0] === line.part_ref;
  const remainder = shouldFollow ? expandTo!.slice(1) : undefined;

  async function toggle() {
    setPanelOpen(true);
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (children !== null) return;

    setLoading(true);
    setFailure(null);
    try {
      const page: Page<TreeLine> = await api.children(
        version,
        line.path,
        calculationId,
      );
      setChildren([...page.items]);
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "échec du dépliage");
    } finally {
      setLoading(false);
    }
  }

  // Recherche : le serveur a renvoyé le chemin, on le suit de proche en proche.
  if (shouldFollow && remainder?.length && !open) {
    void toggle();
  }

  const modified = line.is_modified === true;
  const inPath = line.has_modified_descendant === true;
  const refused = useContext(Refusals).get(line.part_ref);

  return (
    <li className="node">
      <div
        className={`row${modified ? " row--modified" : ""}${
          inPath ? " row--in-modified-path" : ""
        }`}
        style={{ paddingLeft: `${depth * 18 + 8}px` }}
      >
        <button
          className="chevron"
          onClick={toggle}
          disabled={!line.has_children}
          aria-expanded={open}
          aria-label={open ? "Replier" : "Déplier"}
        >
          {line.has_children ? (open ? "▾" : "▸") : "·"}
        </button>

        <button
          className="label"
          onClick={() => setPanelOpen((shown) => !shown)}
          title="Régler cette pièce"
          aria-expanded={panelOpen}
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

      {panelOpen && scenarioId && (
        <NodePanel
          line={line}
          version={version}
          scenarioId={scenarioId}
          depth={depth}
          onChanged={onParameterChanged}
        />
      )}

      {open && (
        <>
          {loading && <p className="hint">chargement…</p>}
          {failure && <p className="hint hint--danger">{failure}</p>}
          {children && children.length > 0 && (
            <ul className="children">
              {children.map((child) => (
                <TreeNode
                  key={child.path}
                  line={child}
                  version={version}
                  scenarioId={scenarioId}
                  calculationId={calculationId}
                  depth={depth + 1}
                  expandTo={remainder}
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
