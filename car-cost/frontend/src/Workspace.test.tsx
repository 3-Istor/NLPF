/**
 * L'onglet 3D, contre le vrai client et un `fetch` simulé avec les réponses
 * de l'API (T10). Seul le rendu WebGL est simulé : jsdom n'a pas de GPU.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PartChange, TreeLine } from "./api/types";
import { mass } from "./format";
import type { ModelViewerProps } from "./model3d/ModelViewer";
import { Workspace } from "./Workspace";

let viewer: ModelViewerProps | null = null;

vi.mock("./model3d/ModelViewer", () => ({
  ModelViewer: (props: ModelViewerProps) => {
    viewer = props;
    return <div data-testid="viewer" />;
  },
}));

const PARENT = "bom-multipla-2026-09-22";
const VARIANT = `${PARENT}+1a2b3c4d`;
const ROOT = "VEH-MULTIPLA-16V";
const GLB = new Uint8Array([0x67, 0x6c, 0x54, 0x46]);

function line(path: string, overrides: Partial<TreeLine> = {}): TreeLine {
  return {
    path,
    part_ref: path.slice(path.lastIndexOf("/") + 1),
    label: `Libellé ${path.slice(path.lastIndexOf("/") + 1)}`,
    system: "CAR",
    valuation_mode: "manufactured",
    unit: "pce",
    edge_quantity: "1.000000",
    has_children: true,
    child_count: 1,
    parent_count: 1,
    occurrence_count: 1,
    ...overrides,
  };
}

const leaf = { has_children: false, child_count: 0 };

const CHILDREN: Record<string, TreeLine[]> = {
  [ROOT]: [line(`${ROOT}/CAR-ASSY`, { child_count: 2 })],
  [`${ROOT}/CAR-ASSY`]: [
    line(`${ROOT}/CAR-ASSY/CAR-HOOD-ASSY`),
    line(`${ROOT}/CAR-ASSY/BODY-SPOILER`, { label: "Aileron arrière", ...leaf }),
  ],
  [`${ROOT}/CAR-ASSY/CAR-HOOD-ASSY`]: [
    line(`${ROOT}/CAR-ASSY/CAR-HOOD-ASSY/CAR-HOOD-SHELL`, { label: "Peau de capot", ...leaf }),
  ],
};

const WHERE_USED: Record<string, string> = {
  "CAR-HOOD-SHELL": `${ROOT}/CAR-ASSY/CAR-HOOD-ASSY/CAR-HOOD-SHELL`,
  "BODY-SPOILER": `${ROOT}/CAR-ASSY/BODY-SPOILER`,
};

const SPOILER: PartChange = {
  part_ref: "BODY-SPOILER",
  label: "Aileron arrière",
  kind: "NEW",
  material_before: null,
  material_after: "MAT-ABS-GRANULE",
  mass_before_kg: null,
  mass_after_kg: "3.150000",
  mass_delta_kg: "3.150000",
  cumulative_quantity: "1.000000000000000000",
  unit_cost_before: null,
  unit_cost_after: "6.523386200000",
};

function calculation(version: string) {
  return {
    id: "calc-v",
    scenario_id: "scn-v",
    status: "OK",
    bom_version: version,
    computed_at: "2026-10-07T08:00:00+00:00",
    input_digest: "sha256:0",
    display_currency: "EUR",
    total_cost: { amount: "5000.00", currency: "EUR" },
    price_snapshot: { id: "snp-1", age_seconds: 10, status: "FRESH" },
    systems: [],
    top_cost_contributors: [],
    total_co2: { kg_co2e: "980.000000" },
    top_co2_contributors: [],
    parts_without_price: [],
    parts_without_co2: [],
    issue_counts: { missing_price: 0, quarantined: 0, fallback: 0 },
  };
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

/** L'API telle que T10 la sert, pour une nomenclature avec ou sans modèle. */
function serve(version: string, withModel: boolean) {
  return vi.fn(async (input: string) => {
    const url = new URL(decodeURIComponent(input), "http://test");
    const route = url.pathname.replace(`/api/v1/bom/${version}`, "BOM");
    const param = (name: string) => url.searchParams.get(name);
    if (url.pathname === "/api/v1/scenarios") {
      return json({
        items: [
          {
            id: "scn-v",
            name: "Scénario de la variante",
            bom_version: version,
            display_currency: "EUR",
            labour_rate: "42.00",
            active_rules: [],
            parameters: [],
            calculation_state: "UP_TO_DATE",
            stale_reason: null,
            last_calculation_id: "calc-v",
          },
        ],
        total: 1,
      });
    }
    if (url.pathname === "/api/v1/calculation-snapshots") return json({ items: [], total: 0 });
    if (url.pathname === "/api/v1/calculations/calc-v") return json(calculation(version));
    if (url.pathname === "/api/v1/price-snapshots/snp-1/quarantine") {
      return json({ snapshot_id: "snp-1", items: [] });
    }
    if (route === "BOM/root") return json(line(ROOT, { parent_count: 0 }));
    if (route === "BOM/children") {
      const items = CHILDREN[param("path")!] ?? [];
      return json({ path: param("path"), items, total: items.length, limit: 50, offset: 0 });
    }
    if (route === "BOM/where-used") {
      const path = WHERE_USED[param("part_ref")!];
      return json({
        part_ref: param("part_ref"),
        occurrence_count: 1,
        items: [{ path, path_labels: path.split("/"), quantity_on_path: "1.000000" }],
        total: 1,
        limit: 50,
        offset: 0,
      });
    }
    if (route === "BOM/parts/BODY-SPOILER") {
      return json({
        part_ref: "BODY-SPOILER",
        label: "Aileron arrière",
        material_ref: "MAT-ABS-GRANULE",
        material_quantity_kg: "3.150000",
        mass_kg: "3.150000",
        composition: [{ part_ref: "FIX-M8-20", label: "Vis M8×20", quantity: "4.000000", unit: "pce" }],
        cumulative_quantity: "1.000000000000000000",
        unit_cost: { amount: "6.523386200000", currency: "EUR" },
        own_unit_cost: { amount: "0.000000000000", currency: "EUR" },
        own_contribution: { amount: "0.000000000000", currency: "EUR" },
      });
    }
    if (route.startsWith("BOM/parts/")) {
      const ref = route.slice("BOM/parts/".length);
      return json({ part_ref: ref, label: ref, material_ref: null, material_quantity_kg: null, mass_kg: null, composition: [] });
    }
    if (route === "BOM/body-changes") {
      return json({
        version,
        parent_version: PARENT,
        changes: [SPOILER],
        cost: null,
        cost_status: "NO_PRICES",
        material_mass_delta_kg: "3.150000",
      });
    }
    if (route === "BOM/model") {
      return withModel
        ? new Response(GLB, { headers: { "Content-Type": "model/gltf-binary" } })
        : json({ error: { code: "MODEL_NOT_FOUND", message: "pas de modèle" } }, 404);
    }
    return json({ error: { code: "NOT_FOUND", message: route } }, 404);
  });
}

let fetchMock: ReturnType<typeof serve>;

function open(version: string, withModel = true) {
  fetchMock = serve(version, withModel);
  vi.stubGlobal("fetch", fetchMock);
  render(
    <Workspace version={version} labourRate="42.00" isVariant={version === VARIANT} onOpenVersion={() => {}} />,
  );
}

async function openTab() {
  fireEvent.click(await screen.findByRole("tab", { name: "3D" }));
}

const requested = (fragment: string) =>
  fetchMock.mock.calls.some(([url]) => decodeURIComponent(url as string).includes(fragment));

beforeEach(() => {
  viewer = null;
  localStorage.clear();
  history.replaceState(null, "", "/");
});

afterEach(() => vi.unstubAllGlobals());

describe("l'onglet 3D", () => {
  it("3D tab shows the viewer for a vehicle with a model", async () => {
    open(PARENT);
    await screen.findByText(`Libellé ${ROOT}`);
    expect(requested("/model")).toBe(false);

    await openTab();

    expect(await screen.findByTestId("viewer")).toBeInTheDocument();
    expect(new Uint8Array(viewer!.model)).toEqual(GLB);
    expect(screen.getByText(`Libellé ${ROOT}`)).toBeInTheDocument();
  });

  it("3D tab says there is no model", async () => {
    open(PARENT, false);
    await openTab();

    expect(await screen.findByText("pas de modèle 3D pour ce véhicule")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer")).toBeNull();
  });

  it("clicking an object reveals its row", async () => {
    open(PARENT);
    await openTab();
    await screen.findByTestId("viewer");

    act(() => viewer!.onPick("CAR-HOOD-SHELL"));

    const path = `${ROOT}/CAR-ASSY/CAR-HOOD-ASSY/CAR-HOOD-SHELL`;
    await waitFor(() => expect(document.getElementById(`node-${path}`)).toHaveAttribute("aria-selected", "true"));
    expect(requested("/where-used?part_ref=CAR-HOOD-SHELL")).toBe(true);
    await waitFor(() => expect(viewer!.selectedRef).toBe("CAR-HOOD-SHELL"));
  });

  it("clicking the spoiler opens its row under CAR-ASSY and its card", async () => {
    open(VARIANT);
    await openTab();
    await screen.findByTestId("viewer");
    await waitFor(() => expect(viewer!.changes).toEqual([SPOILER]));

    act(() => viewer!.onPick("BODY-SPOILER"));

    const row = await waitFor(() => {
      const found = document.getElementById(`node-${ROOT}/CAR-ASSY/BODY-SPOILER`);
      expect(found).toHaveAttribute("aria-selected", "true");
      return found!;
    });
    expect(row).toHaveAttribute("aria-level", "3");
    expect(document.getElementById(`node-${ROOT}/CAR-ASSY`)).toHaveAttribute("aria-expanded", "true");
    expect(requested("/where-used?part_ref=BODY-SPOILER")).toBe(true);
    expect(requested(`/bom/${VARIANT}/parts/BODY-SPOILER?calculation_id=calc-v`)).toBe(true);

    const card = await screen.findByRole("region", { name: "Fiche pièce" });
    expect(screen.getByTestId("viewer")).toBeInTheDocument();
    expect(within(card).getByText("MAT-ABS-GRANULE")).toBeInTheDocument();
    expect(within(card).getByText(mass("3.150000"))).toBeInTheDocument();
    expect(within(card).getByText("FIX-M8-20").closest("li")).toHaveTextContent(/× 4 pce/);
    expect(within(card).getAllByText(/6,52/).length).toBeGreaterThan(0);
  });
});
