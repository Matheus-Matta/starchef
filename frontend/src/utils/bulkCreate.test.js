import { describe, expect, it } from "vitest";

import { buildBulkPayload, createBulkForm, missingBulkScope } from "./bulkCreate";

describe("escopo da criação em lote", () => {
  it("exige restaurante para mesas e comandas quando o topo está em Todos", () => {
    const form = createBulkForm();

    expect(missingBulkScope("tables", form)).toBe("restaurant");
    expect(missingBulkScope("commands", form)).toBe("restaurant");
  });

  it("exige setor depois do restaurante apenas para mesas", () => {
    const form = createBulkForm("restaurant-2");

    expect(missingBulkScope("tables", form)).toBe("sector");
    expect(missingBulkScope("commands", form)).toBeNull();
  });

  it("envia restaurante e setor corretos ao criar mesas", () => {
    const form = {
      ...createBulkForm("restaurant-2"),
      sector_id: "sector-9",
      from_number: 1,
      to_number: 20,
    };

    expect(buildBulkPayload("tables", form)).toEqual({
      restaurant: "restaurant-2",
      sector: "sector-9",
      from_number: 1,
      to_number: 20,
    });
  });
});
