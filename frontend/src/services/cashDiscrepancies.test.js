import { describe, expect, it } from "vitest";

import { availableDecisions, buildPayload, totalInCents } from "./cashDiscrepancies";

describe("divergência de vendas: contas do lado do navegador", () => {
  it("soma em centavos, sem o erro do ponto flutuante", () => {
    // 0.1 + 0.2 em float é 0.30000000000000004: o total mostrado erraria.
    expect(totalInCents({ a: 0.1, b: 0.2 })).toBe(30);
    expect(totalInCents({ pix: 2000, cartao: 1000, dinheiro: 500 })).toBe(350000);
    expect(totalInCents({ vazio: null, nada: undefined, zero: 0 })).toBe(0);
  });

  it("manda só as formas preenchidas, com duas casas, e o motivo sem espaços", () => {
    const payload = buildPayload({
      cashRegister: "s1",
      amounts: { pix: 2000, cartao: 0, dinheiro: 12.5, nulo: null },
      reason: "  Movimento alto  ",
      notes: "",
    });

    expect(payload).toEqual({
      cash_register: "s1",
      reason: "Movimento alto",
      notes: "",
      by_payment_method: [
        { payment_method: "pix", amount: "2000.00" },
        { payment_method: "dinheiro", amount: "12.50" },
      ],
    });
  });

  it("cada estado oferece só o que o backend aceita", () => {
    expect(availableDecisions("open")).toEqual(["review", "regularize", "cancel"]);
    expect(availableDecisions("reviewed")).toEqual(["regularize", "cancel"]);
    expect(availableDecisions("regularized")).toEqual([]);
    expect(availableDecisions("cancelled")).toEqual([]);
  });
});
