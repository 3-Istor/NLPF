/**
 * La barre de recherche, contre une API simulée : le compteur parle en
 * occurrences, suivant et précédent parcourent les chemins servis, une erreur
 * se voit.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiFailure } from "../api/client";
import type { SearchHit, SearchResponse } from "../api/types";
import { SearchBar } from "./SearchBar";

vi.mock("../api/client", () => ({
  ApiFailure: class extends Error {
    constructor(
      readonly code: string,
      message: string,
      readonly status: number,
    ) {
      super(message);
    }
  },
  api: { search: vi.fn() },
}));

const VERSION = "bom-test";
const search = vi.mocked(api.search);

function hit(part_ref: string, label: string, paths: string[]): SearchHit {
  return {
    part_ref,
    label,
    system: "ELE",
    occurrence_count: paths.length,
    paths,
    paths_truncated: false,
  };
}

const THREE: SearchResponse = {
  items: [
    hit("HARNESS", "Faisceau électrique", ["V/A/H", "V/B/H"]),
    hit("RACK", "Support électrique", ["V/C/R"]),
  ],
  total_parts: 2,
  total_occurrences: 3,
};

const onNavigate = vi.fn();
const onQueryChange = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  search.mockResolvedValue(THREE);
});

function mount() {
  render(
    <SearchBar version={VERSION} onNavigate={onNavigate} onQueryChange={onQueryChange} />,
  );
  return screen.getByRole("searchbox");
}

async function searchFor(text: string) {
  const input = mount();
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: "Enter" });
  return input;
}

describe("SearchBar", () => {
  it("le compteur parle en occurrences", async () => {
    await searchFor("electrique");

    expect(await screen.findByText("1 / 3 résultats (2 pièces)")).toBeInTheDocument();
    expect(onNavigate).toHaveBeenCalledWith("V/A/H");
    expect(search).toHaveBeenCalledWith(VERSION, "electrique", 50);
    expect(onQueryChange).toHaveBeenLastCalledWith("electrique");
  });

  it("Entrée passe au suivant, Maj+Entrée revient", async () => {
    const input = await searchFor("electrique");
    await screen.findByText("1 / 3 résultats (2 pièces)");

    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByText("2 / 3 résultats (2 pièces)")).toBeInTheDocument();
    expect(onNavigate).toHaveBeenLastCalledWith("V/B/H");

    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(screen.getByText("1 / 3 résultats (2 pièces)")).toBeInTheDocument();
    expect(onNavigate).toHaveBeenLastCalledWith("V/A/H");
    expect(search).toHaveBeenCalledTimes(1);

    // Les boutons font de même, et précédent boucle à la fin.
    fireEvent.click(screen.getByRole("button", { name: "Résultat précédent" }));
    expect(screen.getByText("3 / 3 résultats (2 pièces)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Résultat suivant" }));
    expect(screen.getByText("1 / 3 résultats (2 pièces)")).toBeInTheDocument();
  });

  it("F3 passe au suivant et boucle", async () => {
    await searchFor("electrique");
    await screen.findByText("1 / 3 résultats (2 pièces)");

    fireEvent.keyDown(window, { key: "F3" });
    expect(screen.getByText("2 / 3 résultats (2 pièces)")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "F3" });
    expect(screen.getByText("3 / 3 résultats (2 pièces)")).toBeInTheDocument();
    expect(onNavigate).toHaveBeenLastCalledWith("V/C/R");
    fireEvent.keyDown(window, { key: "F3" });
    expect(screen.getByText("1 / 3 résultats (2 pièces)")).toBeInTheDocument();
    expect(onNavigate).toHaveBeenLastCalledWith("V/A/H");

    fireEvent.keyDown(window, { key: "F3", shiftKey: true });
    expect(screen.getByText("3 / 3 résultats (2 pièces)")).toBeInTheDocument();
  });

  it("une erreur de recherche est affichée", async () => {
    search.mockRejectedValue(
      new ApiFailure("BOM_VERSION_NOT_FOUND", "version inconnue", 404),
    );

    await searchFor("electrique");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("version inconnue");
    expect(alert).toHaveTextContent("BOM_VERSION_NOT_FOUND");
    expect(screen.queryByText(/résultats? \(/)).toBeNull();
    expect(screen.queryByText(/\d+ \/ \d+/)).toBeNull();
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("aucun résultat", async () => {
    search.mockResolvedValue({ items: [], total_parts: 0, total_occurrences: 0 });

    await searchFor("introuvable");

    expect(await screen.findByText("0 résultat")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Résultat suivant" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Résultat précédent" })).toBeDisabled();
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("liste tronquée", async () => {
    const paths = Array.from({ length: 50 }, (_, i) => `V/S/${i}`);
    search.mockResolvedValue({
      items: [{ ...hit("SCREW", "Vis M6", paths), occurrence_count: 60, paths_truncated: true }],
      total_parts: 1,
      total_occurrences: 60,
    });

    await searchFor("vis");

    expect(
      await screen.findByText("1 / 60 résultats (1 pièces), 50 parcourables"),
    ).toBeInTheDocument();
  });

  it("vider le champ efface", async () => {
    const input = await searchFor("electrique");
    await screen.findByText("1 / 3 résultats (2 pièces)");

    fireEvent.change(input, { target: { value: "" } });

    expect(screen.queryByText(/\/ 3 résultats/)).toBeNull();
    expect(onQueryChange).toHaveBeenLastCalledWith("");
    // Plus rien à parcourir : F3 ne navigue plus.
    onNavigate.mockClear();
    act(() => {
      fireEvent.keyDown(window, { key: "F3" });
    });
    expect(onNavigate).not.toHaveBeenCalled();
  });
});

describe("recherche à la frappe", () => {
  afterEach(() => vi.useRealTimers());

  const settle = () => act(async () => { await vi.advanceTimersByTimeAsync(300); });

  it("chaque frappe relance la recherche, sans Entrée", async () => {
    vi.useFakeTimers();
    const input = mount();

    fireEvent.change(input, { target: { value: "elec" } });
    expect(search).not.toHaveBeenCalled();
    await settle();

    expect(search).toHaveBeenCalledWith(VERSION, "elec", 50);
    expect(screen.getByText("1 / 3 résultats (2 pièces)")).toBeInTheDocument();
    expect(onQueryChange).toHaveBeenLastCalledWith("elec");
  });

  it("une frappe rapide ne lance qu'une recherche, la dernière", async () => {
    vi.useFakeTimers();
    const input = mount();

    fireEvent.change(input, { target: { value: "el" } });
    fireEvent.change(input, { target: { value: "ele" } });
    fireEvent.change(input, { target: { value: "elec" } });
    await settle();

    expect(search).toHaveBeenCalledTimes(1);
    expect(search).toHaveBeenCalledWith(VERSION, "elec", 50);
  });

  it("une seule lettre ne cherche pas", async () => {
    vi.useFakeTimers();
    const input = mount();

    fireEvent.change(input, { target: { value: "e" } });
    await settle();

    expect(search).not.toHaveBeenCalled();
  });

  it("une réponse arrivée après une plus récente est ignorée", async () => {
    vi.useFakeTimers();
    let late: (value: SearchResponse) => void = () => {};
    search.mockImplementationOnce(() => new Promise((resolve) => { late = resolve; }));
    const recent: SearchResponse = {
      items: [hit("RACK", "Support électrique", ["V/C/R"])],
      total_parts: 1,
      total_occurrences: 1,
    };
    search.mockResolvedValueOnce(recent);
    const input = mount();

    fireEvent.change(input, { target: { value: "el" } });
    await settle();
    fireEvent.change(input, { target: { value: "support" } });
    await settle();
    await act(async () => { late(THREE); });

    expect(screen.getByText("1 / 1 résultats (1 pièces)")).toBeInTheDocument();
    expect(onQueryChange).toHaveBeenLastCalledWith("support");
  });
});
