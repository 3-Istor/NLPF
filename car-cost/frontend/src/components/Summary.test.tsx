/**
 * La synthèse d'un calcul fait sur des prix dégradés.
 *
 * Le total seul ne suffit pas : l'utilisateur doit savoir combien de prix ne
 * sont pas frais, lesquels, et pouvoir aller les voir dans l'arbre.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Calculation, QuarantineJournal } from "../api/types";
import { Summary } from "./Summary";

const degraded: Calculation = {
  id: "calc-1",
  scenario_id: "scn-1",
  status: "DEGRADED",
  bom_version: "bom-test",
  computed_at: "2026-09-24T09:00:00+00:00",
  input_digest: "sha256:0",
  display_currency: "EUR",
  total_cost: { amount: "13285.661001", currency: "EUR" },
  price_snapshot: { id: "snp-jour", age_seconds: 30, status: "DEGRADED" },
  systems: [],
  top_cost_contributors: [],
  parts_without_price: [],
  issue_counts: { missing_price: 0, quarantined: 1, fallback: 2 },
};

const journal: QuarantineJournal = {
  snapshot_id: "snp-jour",
  items: [
    {
      part_ref: "ALT-BEARING",
      currency: "EUR",
      rejected_value: "-42.000000",
      reason: "prix négatif",
      replacement: { amount: "4.200000", currency: "EUR" },
      replacement_from_snapshot: "snp-hier",
      detected_at: "2026-09-24T08:33:42+00:00",
    },
  ],
};

function mount(
  overrides: { journal?: QuarantineJournal | null; onGoToPart?: (ref: string) => void } = {},
) {
  return render(
    <Summary
      calculation={degraded}
      journal={overrides.journal === undefined ? journal : overrides.journal}
      state="UP_TO_DATE"
      staleReason={null}
      busy={false}
      failure={null}
      onRecalculate={() => {}}
      onGoToPath={() => {}}
      onGoToPart={overrides.onGoToPart ?? (() => {})}
    />,
  );
}

describe("prix dégradés", () => {
  it("dit combien de prix ne sont pas frais, et de quelle façon", () => {
    mount();

    expect(
      screen.getByText(/1 prix en quarantaine, 2 prix de repli/),
    ).toBeInTheDocument();
  });

  it("montre ce qui a été refusé, pourquoi, et ce qui a été retenu", () => {
    mount();

    expect(screen.getByText("« -42.000000 » refusé : prix négatif")).toBeInTheDocument();
    // Le prix de référence, pas le coût unitaire de la ligne : fournisseur
    // et usine s'appliquent ensuite (ADR-0010), et la ligne affiche un autre
    // montant. Le libellé doit le dire, sinon les deux chiffres se contredisent.
    expect(screen.getByText("référence retenue 4,20 €")).toBeInTheDocument();
  });

  it("mène jusqu'à la pièce refusée dans l'arbre", () => {
    const onGoToPart = vi.fn();
    mount({ onGoToPart });

    fireEvent.click(screen.getByRole("button", { name: "ALT-BEARING" }));

    expect(onGoToPart).toHaveBeenCalledWith("ALT-BEARING");
  });

  it("dit que le journal manque plutôt que de se taire", () => {
    mount({ journal: null });

    expect(screen.getByText(/journal de quarantaine n'a pas pu être lu/)).toBeInTheDocument();
  });
});

describe("aucun prix disponible", () => {
  const NO_PRICES_TEXT =
    "Aucun snapshot de prix disponible : aucun calcul n'est possible.";

  function mountState(state: "NO_PRICES" | "UP_TO_DATE") {
    return render(
      <Summary
        calculation={state === "NO_PRICES" ? null : degraded}
        journal={null}
        state={state}
        staleReason={null}
        busy={false}
        failure={null}
        onRecalculate={() => {}}
        onGoToPath={() => {}}
        onGoToPart={() => {}}
      />,
    );
  }

  it("explique qu'aucun calcul n'est possible sans snapshot de prix", () => {
    const { container } = mountState("NO_PRICES");

    expect(container.querySelector(".banner")).toHaveTextContent(NO_PRICES_TEXT);
  });

  it("pas de bandeau NO_PRICES quand le calcul est à jour", () => {
    mountState("UP_TO_DATE");

    expect(screen.queryByText(NO_PRICES_TEXT)).not.toBeInTheDocument();
  });
});

describe("un échec se dit à voix haute", () => {
  it("la bannière d'erreur est une alerte", () => {
    render(
      <Summary
        calculation={degraded}
        journal={journal}
        state="UP_TO_DATE"
        staleReason={null}
        busy={false}
        failure="SNAPSHOT_NAME_TAKEN — le nom est déjà pris"
        onRecalculate={() => {}}
        onGoToPath={() => {}}
        onGoToPart={() => {}}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("le nom est déjà pris");
  });
});
