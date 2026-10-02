import { describe, expect, it } from "vitest";

import { linhaDoHistorico } from "./commandHistory";

describe("linha do histórico da comanda", () => {
  it("mostra item, valor, autor com código do operador, conta e motivo", () => {
    const linha = linhaDoHistorico({
      at: "2026-10-01T15:21:00-03:00",
      kind: "voided",
      label: "Cancelado",
      user: "Maria Silva",
      operator_code: "4821",
      item: { id: "i1", product: "X-Burger", quantity: "2.000", total: "50.00" },
      order: { id: "o1", sequence: 88 },
      table: "5",
      reason: "Cliente desistiu",
    });

    expect(linha.acao).toBe("Cancelado");
    expect(linha.item).toMatch(/^2× X-Burger · R\$\s?50,00$/);
    expect(linha.quem).toBe("Maria Silva · código 4821");
    expect(linha.conta).toBe("#88");
    expect(linha.mesa).toBe("Mesa 5");
    expect(linha.motivo).toBe("Cliente desistiu");
  });

  it("evento sem item nem autor (produção automática) não inventa texto", () => {
    const linha = linhaDoHistorico({ at: "2026-10-01T15:21:00Z", kind: "ready", label: "Pronto", user: "", operator_code: "", item: null, order: null, table: null, reason: "" });

    expect(linha.item).toBe("");
    expect(linha.quem).toBe("—");
    expect(linha.conta).toBe("");
  });

  it("peso aparece com casas decimais", () => {
    const linha = linhaDoHistorico({ at: "2026-10-01T15:21:00Z", kind: "launched", label: "Lançado", item: { id: "i", product: "Buffet", quantity: "0.452", total: "31.64" } });

    expect(linha.item).toContain("0,452× Buffet");
  });
});
