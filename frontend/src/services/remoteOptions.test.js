import { describe, expect, it, vi } from "vitest";

import { loadRemoteOptions } from "./remoteOptions";

describe("opções remotas dos formulários", () => {
  it("busca uma vez quando dois campos usam o mesmo endpoint e escopo", async () => {
    const get = vi.fn(async () => ({
      data: { results: [{ id: "1", name: "Bebidas", code: "BEB" }] },
    }));

    const options = await loadRemoteOptions([
      { name: "category", type: "remote-dropdown", endpoint: "/menu/categories/" },
      {
        name: "source_category",
        type: "remote-dropdown",
        endpoint: "/menu/categories/",
        optionLabel: "code",
      },
    ], get);

    expect(get).toHaveBeenCalledTimes(1);
    expect(options.category).toEqual([
      { label: "Bebidas", value: "1", group: "", description: "" },
    ]);
    expect(options.source_category[0].label).toBe("BEB");
  });

  it("mantém separados o endpoint global e o filtrado por restaurante", async () => {
    const get = vi.fn(async () => ({ data: [] }));

    await loadRemoteOptions([
      { name: "local", type: "remote-dropdown", endpoint: "/restaurants/" },
      { name: "global", type: "remote-dropdown", endpoint: "/restaurants/", globalScope: true },
    ], get);

    expect(get).toHaveBeenCalledTimes(2);
  });
});
