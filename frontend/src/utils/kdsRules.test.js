import { describe, expect, it } from "vitest";

import { fieldValues, ruleSummary } from "./kdsRules";

describe("kdsRules", () => {
  it("descreve uma regra de pagamento com destino", () => {
    const rule = {
      action: "move",
      target_column: "paid",
      match: "all",
      conditions: [{ field: "payment_status", operator: "equals", value: "paid" }],
    };
    expect(ruleSummary(rule, [{ id: "paid", name: "Pagos" }])).toContain("Mover para Pagos");
    expect(ruleSummary(rule, [{ id: "paid", name: "Pagos" }])).toContain("Status do pagamento Pago");
  });

  it("oferece tipos de pedido para a condição", () => {
    expect(fieldValues("order_type")).toContainEqual({ value: "delivery", label: "Delivery" });
  });

  it("permite editar as exclusões de cancelados dos modelos", () => {
    expect(fieldValues("order_status")).toContainEqual({ value: "cancelled", label: "Cancelado" });
    expect(fieldValues("order_status")).toContainEqual({ value: "refunded", label: "Estornado" });
    expect(fieldValues("item_status")).toContainEqual({ value: "cancelled", label: "Cancelado" });
  });
});
