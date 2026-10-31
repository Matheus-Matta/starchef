import { describe, expect, it } from "vitest";

import { cartoesDaVisaoGeral } from "./cartoes";

describe("cartões da Visão Geral", () => {
  it("separa os dados do período da operação atual", () => {
    const cartoes = cartoesDaVisaoGeral(
      { vendido: "80.00", pedidos: 3, pedidos_pagos: 2, ticket_medio: "40.00", pedidos_cancelados: 0 },
      { em_uso: 3, em_uso_valor: "55.50", pagas: 2, usadas: 4, itens_lancados: 7 },
    );

    expect(cartoes.filter((c) => c.grupo === "periodo").map((c) => c.chave)).toEqual([
      "vendido", "pedidos", "pedidos_pagos", "ticket",
    ]);
    expect(cartoes.filter((c) => c.grupo === "agora").map((c) => c.chave)).toEqual([
      "comandas_em_uso", "comandas_pagas", "comandas_usadas", "ticket_comanda",
    ]);
    expect(cartoes.find((c) => c.chave === "comandas_em_uso").legenda).toContain("55,50");
    expect(cartoes.find((c) => c.chave === "comandas_usadas").legenda).toBe("7 itens lançados");
  });

  it("mantém os indicadores principais visíveis quando o dia está zerado", () => {
    const cartoes = cartoesDaVisaoGeral(
      { vendido: "0.00", pedidos: 0, pedidos_pagos: 0, ticket_medio: "0.00" },
      { em_uso: 0, pagas: 0, usadas: 0, ticket_medio: "0.00" },
    );

    expect(cartoes).toHaveLength(8);
    expect(cartoes.find((c) => c.chave === "pedidos_pagos").valor).toBe("0");
    expect(cartoes.find((c) => c.chave === "comandas_em_uso").valor).toBe("0");
  });
});
