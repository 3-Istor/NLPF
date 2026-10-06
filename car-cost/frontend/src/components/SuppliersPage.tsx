/**
 * Les fournisseurs de la nomenclature ouverte, et ce que chacun vend.
 *
 * À gauche les fournisseurs, à droite les pièces du fournisseur choisi, et
 * sous elles la courbe de prix de la pièce cliquée. Le fournisseur et la
 * pièce vivent dans l'URL : un F5 rouvre le même graphe.
 */

import { useEffect, useMemo, useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { SupplierParts, SupplierSummary } from "../api/types";
import { money } from "../format";
import { PriceChart } from "./PriceChart";

type Props = { version: string };

function readParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

function writeParams(changes: Record<string, string | null>) {
  const params = new URLSearchParams(window.location.search);
  for (const [name, value] of Object.entries(changes)) {
    if (value) params.set(name, value);
    else params.delete(name);
  }
  const url = `${window.location.pathname}?${params}${window.location.hash}`;
  window.history.replaceState(window.history.state, "", url);
}

export function SuppliersPage({ version }: Props) {
  const [suppliers, setSuppliers] = useState<SupplierSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(readParam("supplier"));
  const [parts, setParts] = useState<SupplierParts | null>(null);
  const [partRef, setPartRef] = useState<string | null>(readParam("part"));
  const [filter, setFilter] = useState("");
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .suppliers(version)
      .then(({ items }) => {
        if (!alive) return;
        setSuppliers(items);
        setSelected((current) =>
          current && items.some((item) => item.supplier_id === current)
            ? current
            : (items[0]?.supplier_id ?? null),
        );
      })
      .catch((error) => alive && setFailure(describe(error)));
    return () => {
      alive = false;
    };
  }, [version]);

  useEffect(() => {
    if (!selected) return;
    let alive = true;
    setParts(null);
    writeParams({ supplier: selected });
    api
      .supplierParts(version, selected)
      .then((body) => alive && setParts(body))
      .catch((error) => alive && setFailure(describe(error)));
    return () => {
      alive = false;
    };
  }, [version, selected]);

  function choosePart(ref: string) {
    setPartRef(ref);
    writeParams({ part: ref });
  }

  const shown = useMemo(() => {
    if (!parts) return [];
    const needle = filter.trim().toLocaleLowerCase("fr-FR");
    if (!needle) return parts.items;
    return parts.items.filter(
      (item) =>
        item.part_ref.toLocaleLowerCase("fr-FR").includes(needle) ||
        item.label.toLocaleLowerCase("fr-FR").includes(needle),
    );
  }, [parts, filter]);

  if (failure && !suppliers) {
    return <p className="banner banner--danger" role="alert">{failure}</p>;
  }
  if (!suppliers) return <p className="hint">chargement des fournisseurs…</p>;

  return (
    <div className="suppliers">
      <nav className="suppliers__list" aria-label="Fournisseurs">
        <h2>Fournisseurs ({suppliers.length})</h2>
        <ul>
          {suppliers.map((supplier) => (
            <li key={supplier.supplier_id}>
              <button
                type="button"
                aria-current={supplier.supplier_id === selected ? "true" : undefined}
                onClick={() => setSelected(supplier.supplier_id)}
              >
                <span className="suppliers__name">{supplier.name}</span>
                <span className="suppliers__count">
                  {supplier.part_count} pièce{supplier.part_count > 1 ? "s" : ""}
                  {supplier.default_count > 0 && ` · retenu pour ${supplier.default_count}`}
                </span>
                <span className="suppliers__plants">
                  {supplier.plants.map((plant) => `${plant.label} (${plant.origin_country})`).join(", ")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <section className="suppliers__detail">
        {parts ? (
          <>
            <header className="suppliers__header">
              <h2>{parts.name}</h2>
              <input
                type="search"
                aria-label="Filtrer les pièces"
                placeholder="filtrer par référence ou libellé"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
              />
            </header>
            {/* Au-dessus de la liste : un fournisseur peut vendre des
                centaines de pièces, la courbe ne doit pas finir hors de vue. */}
            {partRef && <PriceChart version={version} partRef={partRef} />}
            <p className="hint">
              {parts.plants.map((plant) => (
                <span key={plant.plant_id} className="suppliers__plant">
                  {plant.label} ({plant.origin_country}) — coefficient {plant.price_coefficient},{" "}
                  {plant.lead_time_days} j{plant.is_default ? ", usine par défaut" : ""}
                </span>
              ))}
            </p>
            <table className="suppliers__parts">
              <thead>
                <tr>
                  <th>Référence</th>
                  <th>Pièce</th>
                  <th>Multiplicateur</th>
                  <th>
                    Prix de référence
                    {parts.price_snapshot && <small> (snapshot {parts.price_snapshot.id})</small>}
                  </th>
                  <th>Retenu</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((item) => (
                  <tr
                    key={item.part_ref}
                    aria-selected={item.part_ref === partRef}
                    onClick={() => choosePart(item.part_ref)}
                  >
                    <td>
                      <button type="button" className="link" onClick={() => choosePart(item.part_ref)}>
                        <code>{item.part_ref}</code>
                      </button>
                    </td>
                    <td>{item.label}</td>
                    <td className="num">× {item.price_multiplier}</td>
                    <td className="num">
                      {money(item.reference_price)} / {item.unit}
                    </td>
                    <td>{item.is_default ? "oui" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {shown.length === 0 && <p className="hint">Aucune pièce ne correspond.</p>}
          </>
        ) : (
          <p className="hint">{failure ?? "chargement des pièces…"}</p>
        )}

      </section>
    </div>
  );
}

function describe(error: unknown): string {
  if (error instanceof ApiFailure) return `${error.code} — ${error.message}`;
  return error instanceof Error ? error.message : "erreur inconnue";
}
