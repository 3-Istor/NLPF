/**
 * Le panneau de saisie, dans le nœud.
 *
 * Il change selon le mode de valorisation, et ce n'est pas de l'ergonomie :
 * proposer un fournisseur sur un ensemble fabriqué serait proposer une double
 * comptabilisation (ADR-0008). Les champs ne sont donc pas grisés — ils ne
 * sont pas là.
 *
 * La portée du réglage est affichée telle que le serveur la formule : l'écran
 * ne la déduit pas, il ne connaît pas le graphe (ADR-0002).
 */

import { useEffect, useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { Supplier, TreeLine } from "../api/types";

type Props = {
  line: TreeLine;
  version: string;
  scenarioId: string;
  depth: number;
  onChanged: () => void;
};

type PartDetail = {
  suppliers?: Supplier[];
};

export function NodePanel({ line, version, scenarioId, depth, onChanged }: Props) {
  const purchased = line.valuation_mode === "purchased";
  const [detail, setDetail] = useState<PartDetail | null>(null);
  const [supplierId, setSupplierId] = useState<string>("");
  const [plantId, setPlantId] = useState<string>("");
  const [scope, setScope] = useState<"part" | "path">("part");
  const [override, setOverride] = useState("");
  const [justification, setJustification] = useState("");
  const [labourMinutes, setLabourMinutes] = useState("");
  const [ack, setAck] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    if (!purchased) return;
    let alive = true;
    api
      .part(version, line.part_ref)
      .then((body) => alive && setDetail(body as PartDetail))
      .catch(() => alive && setDetail({ suppliers: [] }));
    return () => {
      alive = false;
    };
  }, [purchased, version, line.part_ref]);

  const suppliers = detail?.suppliers ?? [];
  const plants =
    suppliers.find((s) => s.supplier_id === supplierId)?.plants ?? [];

  async function apply(body: Record<string, unknown>) {
    setFailure(null);
    try {
      const target = scope === "path" ? line.path : line.part_ref;
      const response = await api.putParameter(scenarioId, target, {
        scope,
        ...body,
      });
      setAck(response.scope_label);
      onChanged();
    } catch (error) {
      setFailure(
        error instanceof ApiFailure ? error.message : "échec de l'enregistrement",
      );
    }
  }

  return (
    <div className="panel" style={{ marginLeft: `${depth * 18 + 34}px` }}>
      <p className="panel__title">
        {purchased ? "Pièce achetée" : "Ensemble fabriqué"} — {line.part_ref}
      </p>

      {purchased ? (
        <>
          <label>
            Fournisseur
            <select
              value={supplierId}
              onChange={(event) => {
                setSupplierId(event.target.value);
                // Changer de fournisseur invalide l'usine : elle appartenait
                // au précédent, et l'API refuserait la combinaison.
                setPlantId("");
              }}
            >
              <option value="">— par défaut —</option>
              {suppliers.map((supplier) => (
                <option key={supplier.supplier_id} value={supplier.supplier_id}>
                  {supplier.name} (×{supplier.price_multiplier})
                </option>
              ))}
            </select>
          </label>

          <label>
            Provenance
            <select
              value={plantId}
              onChange={(event) => setPlantId(event.target.value)}
              disabled={!supplierId}
            >
              <option value="">— site par défaut —</option>
              {plants.map((plant) => (
                <option key={plant.plant_id} value={plant.plant_id}>
                  {plant.label} ({plant.origin_country}) ×{plant.price_coefficient}
                  {" — "}
                  {plant.lead_time_days} j
                </option>
              ))}
            </select>
          </label>

          <label className="panel__wide">
            Prix forcé
            <span className="panel__inline">
              <input
                type="text"
                inputMode="decimal"
                placeholder="ex. 29.99"
                value={override}
                onChange={(event) => setOverride(event.target.value)}
              />
              <input
                type="text"
                placeholder="justification (obligatoire)"
                value={justification}
                onChange={(event) => setJustification(event.target.value)}
              />
            </span>
          </label>
        </>
      ) : (
        <>
          <p className="panel__note">
            Un ensemble n'a ni fournisseur, ni prix propre : son coût est la
            somme de ses composants et de sa main-d'œuvre.
          </p>
          <label>
            Temps de main-d'œuvre (min)
            <input
              type="text"
              inputMode="decimal"
              placeholder="ex. 12.5"
              value={labourMinutes}
              onChange={(event) => setLabourMinutes(event.target.value)}
            />
          </label>
        </>
      )}

      <fieldset className="scope">
        <legend>Portée du réglage</legend>
        <label>
          <input
            type="radio"
            checked={scope === "part"}
            onChange={() => setScope("part")}
          />
          toutes les occurrences ({line.occurrence_count})
        </label>
        <label>
          <input
            type="radio"
            checked={scope === "path"}
            onChange={() => setScope("path")}
          />
          cette occurrence uniquement
        </label>
      </fieldset>

      <div className="panel__actions">
        <button
          onClick={() =>
            apply(
              purchased
                ? {
                    supplier_id: supplierId || null,
                    plant_id: plantId || null,
                    price_override: override || null,
                    price_override_justification: justification || null,
                  }
                : { labour_minutes: labourMinutes || null },
            )
          }
        >
          Appliquer
        </button>
        {ack && <span className="panel__ack">{ack}</span>}
        {failure && <span className="panel__failure">{failure}</span>}
      </div>
    </div>
  );
}
