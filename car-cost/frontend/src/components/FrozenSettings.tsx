/**
 * Les réglages d'une ligne tels que le snapshot de calcul ouvert les a copiés.
 *
 * Lecture seule : un snapshot ne se modifie pas (ADR-0014). Ce qui est montré
 * vient de la copie, jamais du scénario vivant, qui a pu changer depuis le gel.
 * Pour retoucher ces réglages, on repart du snapshot dans un scénario neuf.
 */

import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CalculationSnapshot, Supplier, TreeLine } from "../api/types";

type Props = {
  line: TreeLine;
  snapshot: CalculationSnapshot;
  version: string;
  depth: number;
};

type Copied = CalculationSnapshot["parameters"][number];

/** La portée est un choix enregistré, dit tel quel ; rien n'est déduit ici. */
const SCOPE_LABELS: Record<Copied["scope"], string> = {
  part: "toutes les occurrences",
  path: "cette occurrence uniquement",
};

export function FrozenSettings({ line, snapshot, version, depth }: Props) {
  const copied = snapshot.parameters.filter((parameter) =>
    parameter.scope === "part"
      ? parameter.part_ref === line.part_ref
      : parameter.path === line.path,
  );
  const needsNames = copied.some((parameter) => parameter.supplier_id);
  const [suppliers, setSuppliers] = useState<readonly Supplier[]>([]);

  useEffect(() => {
    if (!needsNames) return;
    let alive = true;
    api
      .part(version, line.part_ref)
      .then((body) => alive && setSuppliers((body.suppliers as Supplier[]) ?? []))
      // Sans les noms, les identifiants copiés restent lisibles.
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [needsNames, version, line.part_ref]);

  const supplierName = (id: string) =>
    suppliers.find((supplier) => supplier.supplier_id === id)?.name ?? id;
  const plantName = (supplierId: string, plantId: string) =>
    suppliers
      .find((supplier) => supplier.supplier_id === supplierId)
      ?.plants.find((plant) => plant.plant_id === plantId)?.label ?? plantId;

  return (
    <section
      className="panel panel--frozen"
      style={{ marginLeft: `${depth * 18 + 34}px` }}
      aria-label={`Réglages figés — ${line.part_ref}`}
    >
      <p className="panel__title">
        Réglages figés dans « {snapshot.name} » — {line.part_ref}
      </p>
      {copied.length === 0 ? (
        <p className="panel__note">
          Aucun réglage sur cette ligne dans ce snapshot : les valeurs par défaut
          du catalogue ont servi.
        </p>
      ) : (
        copied.map((parameter) => (
          <dl key={`${parameter.scope}-${parameter.path ?? ""}`} className="panel__frozen">
            <dt>Portée</dt>
            <dd>{SCOPE_LABELS[parameter.scope]}</dd>
            {parameter.supplier_id && (
              <>
                <dt>Fournisseur</dt>
                <dd>{supplierName(parameter.supplier_id)}</dd>
              </>
            )}
            {parameter.supplier_id && parameter.plant_id && (
              <>
                <dt>Usine</dt>
                <dd>{plantName(parameter.supplier_id, parameter.plant_id)}</dd>
              </>
            )}
            {parameter.price_override && (
              <>
                <dt>Prix forcé</dt>
                <dd>
                  {parameter.price_override} — {parameter.price_override_justification}
                </dd>
              </>
            )}
            {parameter.labour_minutes && (
              <>
                <dt>Main-d'œuvre</dt>
                <dd>{parameter.labour_minutes} min</dd>
              </>
            )}
            {parameter.purchase_currency && (
              <>
                <dt>Devise d'achat</dt>
                <dd>{parameter.purchase_currency}</dd>
              </>
            )}
          </dl>
        ))
      )}
    </section>
  );
}
