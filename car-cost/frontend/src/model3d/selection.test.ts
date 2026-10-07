import { describe, expect, it } from "vitest";
import type { PartChange } from "../api/types";
import { colored, highlighted, refOf, refOfPath } from "./selection";

const objects = [
  { id: "a", ref: "CAR-PANEL-SIDE" },
  { id: "b", ref: "CAR-PANEL-SIDE" },
  { id: "c", ref: "CAR-HOOD-SHELL" },
  { id: "d", ref: null },
  { id: "e", ref: "BODY-SPOILER" },
];

const spoiler: PartChange = {
  part_ref: "BODY-SPOILER",
  label: "Aileron",
  kind: "NEW",
  material_before: null,
  material_after: "MAT-ABS-GRANULE",
  mass_before_kg: null,
  mass_after_kg: "3.150000",
  mass_delta_kg: "3.150000",
  cumulative_quantity: "1",
  unit_cost_before: null,
  unit_cost_after: "6.523386200000",
};

describe("refOf", () => {
  it("reads the part reference that the glTF extras carry", () => {
    expect(refOf({ carcost: { ref: "CAR-HOOD-SHELL" } })).toBe("CAR-HOOD-SHELL");
  });

  it("treats anything else as decor", () => {
    expect(refOf({})).toBeNull();
    expect(refOf(null)).toBeNull();
    expect(refOf({ carcost: {} })).toBeNull();
    expect(refOf({ carcost: { ref: 3 } })).toBeNull();
  });
});

describe("refOfPath", () => {
  it("keeps the last segment of a tree path", () => {
    expect(refOfPath("VEH-MULTIPLA-16V/CAR-ASSY/CAR-HOOD-ASSY/CAR-HOOD-SHELL")).toBe("CAR-HOOD-SHELL");
    expect(refOfPath(null)).toBeNull();
  });
});

describe("highlighted", () => {
  it("lights every object of the selected part", () => {
    expect(highlighted(objects, "CAR-PANEL-SIDE")).toEqual(new Set(["a", "b"]));
  });

  it("lights nothing for a part absent from the model", () => {
    expect(highlighted(objects, "CAR-ABSENT")).toEqual(new Set());
    expect(highlighted(objects, null)).toEqual(new Set());
  });
});

describe("colored", () => {
  it("colours the objects of the parts the variant changed", () => {
    expect(colored(objects, [spoiler])).toEqual(new Set(["e"]));
  });

  it("colours nothing without changes", () => {
    expect(colored(objects, [])).toEqual(new Set());
  });
});
