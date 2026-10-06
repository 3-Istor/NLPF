/**
 * Le panneau de saisie, dans le nœud.
 *
 * Il change selon le mode de valorisation, et ce n'est pas de l'ergonomie :
 * proposer un fournisseur sur un ensemble fabriqué serait proposer une double
 * comptabilisation (ADR-0008). Les champs ne sont donc pas grisés — ils ne
 * sont pas là.
 *
 * Les listes s'ouvrent sur ce qui est réellement retenu : le réglage
 * enregistré du scénario s'il y en a un, sinon le fournisseur et le site par
 * défaut du catalogue. Un « — par défaut — » ne disait pas lequel.
 *
 * La portée du réglage est affichée telle que le serveur la formule : l'écran
 * ne la déduit pas, il ne connaît pas le graphe (ADR-0002).
 */

import { useEffect, useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { Scenario, ScenarioParameter, Supplier, TreeLine } from "../api/types";
import { editable, money, quantity } from "../format";

type Props = {
  line: TreeLine;
  version: string;
  scenario: Scenario;
  depth: number;
  onChanged: () => void;
};

type PartDetail = {
  suppliers?: Supplier[];
  labour_minutes?: string | null;
};

/**
 * Le paramètre qui s'applique à cette occurrence : celui du chemin gagne en
 * entier sur celui de la pièce (`Scenario.parameter_for` côté serveur).
 */
function savedFor(line: TreeLine, scenario: Scenario): ScenarioParameter | undefined {
  return (
    scenario.parameters.find((p) => p.scope === "path" && p.path === line.path) ??
    scenario.parameters.find((p) => p.scope === "part" && p.part_ref === line.part_ref)
  );
}

function defaultPlant(supplier: Supplier | undefined): string {
  const plants = supplier?.plants ?? [];
  return (plants.find((plant) => plant.is_default) ?? plants[0])?.plant_id ?? "";
}

export function NodePanel({ line, version, scenario, depth, onChanged }: Props) {
  const purchased = line.valuation_mode === "purchased";
  const saved = savedFor(line, scenario);
  const [detail, setDetail] = useState<PartDetail | null>(null);
  const [supplierId, setSupplierId] = useState<string>("");
  const [plantId, setPlantId] = useState<string>("");
  const [scope, setScope] = useState<"part" | "path">(saved?.scope ?? "part");
  const [override, setOverride] = useState(
    saved?.price_override ? editable(saved.price_override) : "",
  );
  const [justification, setJustification] = useState(
    saved?.price_override_justification ?? "",
  );
  const [labourMinutes, setLabourMinutes] = useState(
    saved?.labour_minutes ? editable(saved.labour_minutes) : "",
  );
  const scenarioRate = editable(scenario.labour_rate);
  const [labourRate, setLabourRate] = useState(
    saved?.labour_rate ? editable(saved.labour_rate) : scenarioRate,
  );
  const [ack, setAck] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    // Le catalogue et l'option retenue arrivent dans le même rendu : posée
    // dans un effet à part, la sélection laissait un rendu où la liste montrait
    // le premier fournisseur venu et aucun site.
    // Le réglage enregistré n'est lu qu'à l'ouverture : le relire après un
    // « Appliquer » écraserait une saisie en cours.
    const receive = (body: PartDetail) => {
      if (!alive) return;
      const list = body.suppliers ?? [];
      const supplier =
        list.find((s) => s.supplier_id === saved?.supplier_id) ??
        list.find((s) => s.is_default) ??
        list[0];
      const plant = supplier?.plants.find((p) => p.plant_id === saved?.plant_id);
      setDetail(body);
      setSupplierId(supplier?.supplier_id ?? "");
      setPlantId(plant?.plant_id ?? defaultPlant(supplier));
      if (!saved?.labour_minutes && body.labour_minutes) {
        setLabourMinutes(editable(body.labour_minutes));
      }
    };
    api
      .part(version, line.part_ref)
      .then((body) => receive(body as PartDetail))
      .catch(() => receive({ suppliers: [] }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, line.part_ref]);

  const suppliers = detail?.suppliers ?? [];
  const standardMinutes = detail?.labour_minutes ?? null;

  const plants =
    suppliers.find((s) => s.supplier_id === supplierId)?.plants ?? [];

  async function apply(body: Record<string, unknown>) {
    setFailure(null);
    try {
      const target = scope === "path" ? line.path : line.part_ref;
      const response = await api.putParameter(scenario.id, target, {
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
              disabled={suppliers.length === 0}
              onChange={(event) => {
                const id = event.target.value;
                setSupplierId(id);
                // Changer de fournisseur invalide l'usine : elle appartenait
                // au précédent, et l'API refuserait la combinaison.
                setPlantId(
                  defaultPlant(suppliers.find((s) => s.supplier_id === id)),
                );
              }}
            >
              {suppliers.length === 0 && (
                <option value="">aucun fournisseur référencé</option>
              )}
              {suppliers.map((supplier) => (
                <option key={supplier.supplier_id} value={supplier.supplier_id}>
                  {supplier.name} (×{supplier.price_multiplier})
                  {supplier.is_default ? " — par défaut" : ""}
                </option>
              ))}
            </select>
          </label>

          <label>
            Provenance
            <select
              value={plantId}
              onChange={(event) => setPlantId(event.target.value)}
              disabled={plants.length === 0}
            >
              {plants.length === 0 && <option value="">aucun site</option>}
              {plants.map((plant) => (
                <option key={plant.plant_id} value={plant.plant_id}>
                  {plant.label} ({plant.origin_country}) ×{plant.price_coefficient}
                  {" — "}
                  {plant.lead_time_days} j
                  {plant.is_default ? " — par défaut" : ""}
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
                value={override}
                onChange={(event) => setOverride(event.target.value)}
              />
              <input
                type="text"
                aria-label="Justification du prix forcé"
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
              value={labourMinutes}
              onChange={(event) => setLabourMinutes(event.target.value)}
            />
          </label>
          <label>
            Taux horaire ({scenario.display_currency}/h)
            <input
              type="text"
              inputMode="decimal"
              value={labourRate}
              onChange={(event) => setLabourRate(event.target.value)}
            />
          </label>
          <p className="panel__note">
            Temps de la nomenclature :{" "}
            {standardMinutes !== null ? quantity(standardMinutes, "min") : "aucun"}
            {" · "}taux horaire du scénario :{" "}
            {money({ amount: scenario.labour_rate, currency: scenario.display_currency })}/h
          </p>
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
                : {
                    labour_minutes: labourMinutes || null,
                    // Le taux du scénario laissé tel quel n'est pas un réglage :
                    // la pièce suivra ses changements futurs.
                    labour_rate:
                      labourRate && labourRate !== scenarioRate ? labourRate : null,
                  },
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
