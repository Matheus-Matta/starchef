import { describe, expect, it } from "vitest";

import { cartoesDaVisaoGeral } from "./cartoes";

// A Visão Geral só mostra o que tem valor: uma manhã sem cancelamento não
// ganha um cartão "Pedidos cancelados: 0".
describe("cartões da Visão Geral", () => {
  it("mostra só os números que chegaram com valor", () => {
    const cartoes = cartoesDaVisaoGeral(
      { vendido: "80.00", pedidos_pagos: 2, ticket_medio: "40.00", pedidos_cancelados: 0 },
      { abertas: 3, abertas_valor: "55.50" },
    );

    expect(cartoes.map((c) => c.chave)).toEqual(["vendido", "ticket", "comandas_abertas"]);
    expect(cartoes[0].legenda).toBe("2 pedidos pagos");
    expect(cartoes[2].legenda).toContain("55,50");
  });

  it("sem movimento, nenhum cartão", () => {
    expect(cartoesDaVisaoGeral({}, {})).toEqual([]);
  });
});
