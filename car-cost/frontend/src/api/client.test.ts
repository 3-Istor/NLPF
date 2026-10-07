import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiFailure } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("le client de variante", () => {
  it("bodyImport sends the raw file", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new Blob([new Uint8Array([1, 2, 3])]);

    await api.bodyImport("bom-multipla-2026-09-22", file);

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/bom/bom-multipla-2026-09-22/body-imports");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(file);
    expect(init.headers).toEqual({ "Content-Type": "application/octet-stream" });
  });

  it("names the variant after the file", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await api.bodyImport("bom-a+1b", new Blob([]), "capot alu.glb");

    expect((fetchMock.mock.calls[0] as unknown[])[0]).toBe(
      "/api/v1/bom/bom-a%2B1b/body-imports?name=capot%20alu.glb",
    );
  });

  it("encodes the + of a variant identifier", async () => {
    const fetchMock = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);

    await api.bodyChanges("bom-a+1b");

    expect((fetchMock.mock.calls[0] as unknown[])[0]).toBe("/api/v1/bom/bom-a%2B1b/body-changes");
  });

  it("keeps the faults of a 422 readable", async () => {
    const faults = [{ code: "MESH_NOT_CLOSED", message: "m", object: "Capot", part_ref: null }];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ error: { code: "BODY_IMPORT_REJECTED", message: "x", details: { faults } } }), {
            status: 422,
          }),
      ),
    );

    const error = await api.bodyImport("v", new Blob([])).catch((e) => e);

    expect(error).toBeInstanceOf(ApiFailure);
    expect(error.details.faults).toEqual(faults);
  });

  it("asks the part card with its calculation", async () => {
    const fetchMock = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);

    await api.partCard("bom-a+1b", "BODY-SPOILER", "calc-1");

    expect((fetchMock.mock.calls[0] as unknown[])[0]).toBe(
      "/api/v1/bom/bom-a%2B1b/parts/BODY-SPOILER?calculation_id=calc-1",
    );
  });
});
