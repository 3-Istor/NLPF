import { describe, expect, it } from "vitest";
import cases from "../../../backend/tests/fold_cases.json";
import { fold, segments } from "./fold";

describe("fold et segments", () => {
  it("le pliage suit la table partagée avec le serveur", () => {
    for (const { input, folded } of cases) {
      expect(fold(input)).toBe(folded);
    }
  });

  it("un segment trouvé garde le texte d'origine", () => {
    expect(segments("Crémaillère de direction", "cremaillere")).toEqual([
      { text: "Crémaillère", match: true },
      { text: " de direction", match: false },
    ]);
  });

  it("une ligature reste entière", () => {
    expect(segments("ﬁltre à huile", "filtre")).toEqual([
      { text: "ﬁltre", match: true },
      { text: " à huile", match: false },
    ]);
  });

  it("toutes les occurrences sont trouvées", () => {
    const found = segments("Vis — vis M6", "VIS").filter((s) => s.match);
    expect(found.map((s) => s.text)).toEqual(["Vis", "vis"]);
  });

  it("requête vide ou absente", () => {
    expect(segments("Châssis", "")).toEqual([{ text: "Châssis", match: false }]);
    expect(segments("Châssis", "zzz")).toEqual([{ text: "Châssis", match: false }]);
  });

  it("le découpage ne perd ni n'ajoute rien", () => {
    for (const { input } of cases) {
      expect(segments(input, "e").map((s) => s.text).join("")).toBe(input);
    }
  });
});
