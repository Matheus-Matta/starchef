import { describe, expect, it, vi } from "vitest";

import { createGetWithCache } from "./apiGetCache";

describe("apiGetCache", () => {
  it("compartilha a mesma chamada enquanto um GET idêntico está em andamento", async () => {
    let resolveRequest;
    const rawGet = vi.fn(() => new Promise((resolve) => { resolveRequest = resolve; }));
    const get = createGetWithCache(rawGet, () => "restaurante-1");

    const first = get("/menu/categories/", { params: { page_size: 100 } });
    const second = get("/menu/categories/", { params: { page_size: 100 } });
    resolveRequest({ data: [{ id: "1" }] });

    await expect(first).resolves.toEqual({ data: [{ id: "1" }] });
    await expect(second).resolves.toEqual({ data: [{ id: "1" }] });
    expect(rawGet).toHaveBeenCalledTimes(1);
  });

  it("reutiliza pelo TTL e permite forçar uma leitura nova", async () => {
    const rawGet = vi.fn().mockResolvedValueOnce({ data: { version: 1 } })
      .mockResolvedValueOnce({ data: { version: 2 } });
    const get = createGetWithCache(rawGet, () => "restaurante-1");

    await get("/reports/sales/", { cacheTtlMs: 15_000 });
    const cached = await get("/reports/sales/", { cacheTtlMs: 15_000 });
    const fresh = await get("/reports/sales/", { cacheTtlMs: 15_000, forceRefresh: true });

    expect(cached.data.version).toBe(1);
    expect(fresh.data.version).toBe(2);
    expect(rawGet).toHaveBeenCalledTimes(2);
  });

  it("descarta o cache quando uma gravação o invalida", async () => {
    const rawGet = vi.fn().mockResolvedValue({ data: [] });
    const get = createGetWithCache(rawGet);

    await get("/restaurants/", { cacheTtlMs: 60_000 });
    await get("/restaurants/", { cacheTtlMs: 60_000 });
    get.clearCache();
    await get("/restaurants/", { cacheTtlMs: 60_000 });

    expect(rawGet).toHaveBeenCalledTimes(2);
  });

  it("não recoloca no cache uma leitura que terminou depois da invalidação", async () => {
    let resolveOldRequest;
    const rawGet = vi.fn()
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOldRequest = resolve; }))
      .mockResolvedValueOnce({ data: { version: 2 } });
    const get = createGetWithCache(rawGet);

    const oldRequest = get("/restaurants/", { cacheTtlMs: 60_000 });
    get.clearCache();
    resolveOldRequest({ data: { version: 1 } });
    await oldRequest;
    const fresh = await get("/restaurants/", { cacheTtlMs: 60_000 });

    expect(fresh.data.version).toBe(2);
    expect(rawGet).toHaveBeenCalledTimes(2);
  });
});
