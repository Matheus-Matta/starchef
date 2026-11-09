import { describe, expect, it } from "vitest";

import { chaveDaTela } from "./chaveDaTela";

const rota = (name, path, query = {}, meta = {}) => ({
  name, path, query, meta, fullPath: `${path}?${new URLSearchParams(query)}`,
});

describe("chaveDaTela", () => {
  it("lista: digitar na busca (mudar a query) não remonta a tela", () => {
    const antes = chaveDaTela(rota("notas-fiscais", "/notas-fiscais", {}, { estadoNaUrl: true }), "r1");
    const depois = chaveDaTela(rota("notas-fiscais", "/notas-fiscais", { busca: "jo" }, { estadoNaUrl: true }), "r1");
    expect(depois).toBe(antes);
  });

  it("tela comum: outro endereço remonta", () => {
    expect(chaveDaTela(rota("caixa", "/caixa", { a: "1" }), "r1"))
      .not.toBe(chaveDaTela(rota("caixa", "/caixa", { a: "2" }), "r1"));
  });

  it("PDV: trocar de etapa não remonta e não perde o pedido", () => {
    expect(chaveDaTela(rota("pdv", "/pdv", { step: "pagamento", order: "9" }), "r1"))
      .toBe(chaveDaTela(rota("pdv", "/pdv", { step: "itens" }), "r1"));
  });

  it("trocar de restaurante remonta qualquer tela", () => {
    const lista = rota("notas-fiscais", "/notas-fiscais", {}, { estadoNaUrl: true });
    expect(chaveDaTela(lista, "r1")).not.toBe(chaveDaTela(lista, "r2"));
  });
});
