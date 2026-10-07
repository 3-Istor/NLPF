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
  total_co2: { kg_co2e: "412.550000" },
  top_co2_contributors: [],
  parts_without_price: [],
  parts_without_co2: [],
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

/**
 * L'empreinte carbone : servie par l'API, jamais recalculée ici. Une somme
 * partielle ne doit pas se lire comme l'empreinte du véhicule, et un CO₂
 * inconnu ne s'affiche jamais comme un zéro.
 */
describe("empreinte carbone", () => {
  const withCo2: Calculation = {
    ...degraded,
    status: "OK",
    issue_counts: { missing_price: 0, quarantined: 0, fallback: 0 },
    systems: [
      {
        system: "GMP",
        cost: { amount: "900.000000", currency: "EUR" },
        cost_share_pct: "60.0",
        co2: { kg_co2e: "300.100000" },
        co2_share_pct: "72.7",
      },
    ],
    top_cost_contributors: [
      {
        part_ref: "ENG-BLOCK-RAW",
        label: "Bloc moteur brut",
        system: "GMP",
        cumulative_quantity: "1",
        own_contribution: { amount: "412.000000", currency: "EUR" },
        share_pct: "27.5",
        first_path: "VEH/GMP/ENG-BLOCK-RAW",
      },
    ],
    top_co2_contributors: [
      {
        part_ref: "BODY-PANEL",
        label: "Panneau de caisse",
        system: "CAI",
        cumulative_quantity: "4",
        own_co2_contribution: { kg_co2e: "88.200000" },
        share_pct: "21.4",
        first_path: "VEH/CAI/BODY-PANEL",
      },
    ],
  };

  function mountCo2(
    calculation: Calculation,
    onGoToPath: (path: string) => void = () => {},
  ) {
    return render(
      <Summary
        calculation={calculation}
        journal={null}
        state="UP_TO_DATE"
        staleReason={null}
        busy={false}
        failure={null}
        onRecalculate={() => {}}
        onGoToPath={onGoToPath}
        onGoToPart={() => {}}
      />,
    );
  }

  it("affiche le total servi par l'API à côté du coût", () => {
    mountCo2(withCo2);

    expect(screen.getByText("Empreinte carbone")).toBeInTheDocument();
    expect(screen.getByText("412,55 kg CO₂e")).toBeInTheDocument();
  });

  it("une somme partielle le dit, et nomme combien de pièces manquent", () => {
    mountCo2({ ...withCo2, parts_without_co2: ["ALT-BEARING", "SCREW-M6"] });

    expect(screen.getByText("Empreinte carbone partielle")).toBeInTheDocument();
    expect(
      screen.getByText(/2 pièce\(s\) sans CO₂ connu, non comptées/),
    ).toBeInTheDocument();
  });

  it("un calcul antérieur au CO₂ ne montre ni total ni zéro", () => {
    mountCo2({ ...withCo2, total_co2: null });

    expect(screen.queryByText(/kg CO₂e/)).not.toBeInTheDocument();
    expect(screen.getByText(/non calculée par ce calcul/)).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "CO₂" })).not.toBeInTheDocument();
  });

  it("par défaut, systèmes et contributeurs parlent en coût", () => {
    mountCo2(withCo2);

    expect(screen.getByRole("radio", { name: "Coût" })).toBeChecked();
    expect(screen.getByText("Bloc moteur brut")).toBeInTheDocument();
    expect(screen.queryByText("Panneau de caisse")).not.toBeInTheDocument();
  });

  it("basculer sur CO₂ montre la part carbone et ses contributeurs", () => {
    const onGoToPath = vi.fn();
    mountCo2(withCo2, onGoToPath);

    fireEvent.click(screen.getByRole("radio", { name: "CO₂" }));

    expect(screen.getByText("300,10 kg CO₂e")).toBeInTheDocument();
    expect(screen.getByText("72,7 %")).toBeInTheDocument();
    expect(screen.queryByText("Bloc moteur brut")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Panneau de caisse" }));
    expect(onGoToPath).toHaveBeenCalledWith("VEH/CAI/BODY-PANEL");
  });
});

describe("une variante de carrosserie", () => {
  it("hides CO₂ on a variant", () => {
    render(
      <Summary
        calculation={degraded}
        journal={null}
        state="UP_TO_DATE"
        staleReason={null}
        busy={false}
        failure={null}
        hideCo2
        onRecalculate={() => {}}
        onGoToPath={() => {}}
        onGoToPart={() => {}}
      />,
    );

    expect(screen.getByText("Coût de fabrication")).toBeInTheDocument();
    expect(screen.queryByText(/CO₂|CO2/)).toBeNull();
  });
});
