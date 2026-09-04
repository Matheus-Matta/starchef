import { describe, expect, it } from "vitest";

import { helpArticles, helpSections } from "./helpCenter";

const expectedArticleIds = [
  "home",
  "pedidos",
  "kds",
  "kds-estacoes",
  "sla",
  "mesas",
  "comandas",
  "caixa",
  "formas-pagamento",
  "clientes",
  "produtos",
  "categorias",
  "adicionais",
  "ingredientes",
  "receitas",
  "cardapios-digitais",
  "zonas-entrega",
  "entregadores",
  "estoque",
  "locais-estoque",
  "fluxo-fiscal",
  "historico-pagamentos",
  "notas-fiscais",
  "perfis-fiscais",
  "configuracao-cosmos",
  "configuracao-focus",
  "restaurantes",
  "setores",
  "usuarios",
  "perfis-acesso",
  "terminais-pdv",
  "impressoras",
  "balancas",
];

describe("help center content", () => {
  it("covers every sidebar topic", () => {
    expect(helpSections.map((section) => section.id)).toEqual([
      "principal",
      "operacao",
      "cardapio",
      "ecommerce",
      "entrega",
      "logistica",
      "financeiro",
      "gestao",
    ]);
    expect(helpArticles.map((article) => article.id)).toEqual(expectedArticleIds);
  });

  it("keeps article ids unique and every guide complete", () => {
    const ids = helpArticles.map((article) => article.id);
    expect(new Set(ids).size).toBe(ids.length);

    helpArticles.forEach((article) => {
      expect(article.title).toBeTruthy();
      expect(article.summary).toBeTruthy();
      expect(article.purpose).toBeTruthy();
      expect(article.steps.length).toBeGreaterThan(0);
      expect(article.data.length).toBeGreaterThan(0);
      expect(article.sectionId).toBeTruthy();
      expect(article.sectionTitle).toBeTruthy();
    });
  });
});
