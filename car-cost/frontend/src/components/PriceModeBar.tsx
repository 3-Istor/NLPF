/**
 * D'où viennent les prix du calcul : en direct de l'API, ou d'un snapshot.
 *
 * En direct, le total suit le marché simulé et n'est jamais enregistré
 * (ADR-0015). « Figer les prix » prend un snapshot des prix actuels et
 * repasse en mode snapshot : le chiffre suivant est rejouable. En mode
 * snapshot, on choisit lequel : le plus récent par défaut.
 */

import type { PriceSnapshotSummary } from "../api/types";

export type PriceMode = "SNAPSHOT" | "LIVE";

type Props = {
  mode: PriceMode;
  /** Un calcul figé est ouvert : on ne change pas ses prix. */
  frozen: boolean;
  busy: boolean;
  /** L'heure de la dernière lecture en direct, à afficher. */
  liveAt: string | null;
  onModeChange: (mode: PriceMode) => void;
  onFreezePrices: () => void;
  snapshots: readonly PriceSnapshotSummary[];
  /** `null` : le plus récent. */
  selectedSnapshotId: string | null;
  onSelectSnapshot: (id: string | null) => void;
};

export function PriceModeBar({
  mode,
  frozen,
  busy,
  liveAt,
  onModeChange,
  onFreezePrices,
  snapshots,
  selectedSnapshotId,
  onSelectSnapshot,
}: Props) {
  return (
    <div className="price-mode" role="group" aria-label="Prix du calcul">
      <span>Prix</span>
      {(["SNAPSHOT", "LIVE"] as const).map((choice) => (
        <label key={choice}>
          <input
            type="radio"
            name="price-mode"
            value={choice}
            checked={mode === choice}
            disabled={frozen}
            onChange={() => onModeChange(choice)}
          />
          {choice === "LIVE" ? "En direct" : "Snapshot"}
        </label>
      ))}
      {mode === "SNAPSHOT" && (
        <select
          aria-label="Snapshot de prix"
          value={selectedSnapshotId ?? ""}
          disabled={busy || frozen || snapshots.length === 0}
          onChange={(event) => onSelectSnapshot(event.target.value || null)}
        >
          <option value="">Le plus récent</option>
          {snapshots.map((snapshot) => (
            <option key={snapshot.id} value={snapshot.id}>
              {snapshot.id} · {snapshot.currency} · {snapshot.status}
            </option>
          ))}
        </select>
      )}
      <button type="button" onClick={onFreezePrices} disabled={busy || frozen}>
        Figer les prix maintenant
      </button>
      {mode === "LIVE" && liveAt && (
        <span className="price-mode__at">lus à {new Date(liveAt).toLocaleTimeString("fr-FR")}</span>
      )}
    </div>
  );
}
