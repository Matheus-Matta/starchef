import { describe, expect, it } from "vitest";

import { resources } from "./resources";

const invoices = resources.find((resource) => resource.name === "notas-fiscais");

describe("lista de notas fiscais", () => {
  it("ordena das mais recentes e oferece filtros de status e emissao", () => {
    expect(invoices.pro.defaultOrdering).toBe("-created_at");
    expect(invoices.pro.filterFields.map((field) => field.name)).toEqual(["status", "emission_type"]);
    expect(invoices.pro.filterFields.every((field) => field.options.length > 1)).toBe(true);
    expect(invoices.pro.filterFields.every((field) => field.compact)).toBe(true);
  });

  it("mostra o pedido no detalhe e oferece reenvio em massa", () => {
    expect(invoices.columns.find((column) => column.key === "order_sequence")).toMatchObject({
      type: "order-link",
      idKey: "order",
      showInList: false,
    });
    expect(invoices.pro.bulkActions).toContainEqual(expect.objectContaining({
      key: "resend-invoices",
      type: "invoice-bulk-resend",
    }));
  });
});
