import { describe, expect, it } from "vitest";

import { resources } from "./resources";

/**
 * O aviso de preço é a única lógica do cadastro de produto que não é declarativa,
 * e ele existe para evitar uma conclusão específica e errada: "o sistema cobrou
 * diferente do que eu cadastrei, logo o sistema está com defeito".
 */
const produto = resources.find((r) => r.name === "cardapio");
const aviso = produto.formFields.find((f) => f.name === "promotional_price").noticeFor;

describe("aviso de preço no cadastro do produto", () => {
  it("cala quando o preço cobrado é o cadastrado", () => {
    expect(aviso({ sale_price: "20.00", current_price: "20.00" })).toBe("");
  });

  it("nomeia a tabela e a regra quando a promoção vem de tabela de desconto", () => {
    // Nomear é o ponto: "está cobrando menos" não diz onde ir para mudar.
    const texto = aviso({
      sale_price: "20.00",
      current_price: "15.00",
      compare_at_price: "30.00",
      promotion: { name: "Refri gelado", table_name: "Happy hour" },
    });
    expect(texto).toContain("Happy hour");
    expect(texto).toContain("Refri gelado");
    // O "de" do encarte (30) aparece mesmo sendo MAIOR que o cadastrado (20).
    expect(texto).toContain("30,00");
    expect(texto).toContain("15,00");
  });

  it("atribui ao próprio cadastro quando não há tabela envolvida", () => {
    const texto = aviso({ sale_price: "20.00", current_price: "15.00" });
    expect(texto).toContain("promocional deste cadastro");
    expect(texto).not.toContain("tabela");
  });

  it("cala quando o produto ainda nao tem preço (formulário novo)", () => {
    expect(aviso({})).toBe("");
  });
});

describe("cadastros de promoção", () => {
  it("expõe as três telas com rota própria", () => {
    const nomes = resources.map((r) => r.name);
    expect(nomes).toContain("tabelas-de-desconto");
    expect(nomes).toContain("regras-de-desconto");
    expect(nomes).toContain("cupons");
  });

  it("o cupom cobra o mínimo em campo próprio, sem taxa e sem entrega", () => {
    const cupom = resources.find((r) => r.name === "cupons");
    const minimo = cupom.formFields.find((f) => f.name === "minimum_order_value");
    // A frase no hint é o que impede o cadastro de supor que taxa conta.
    expect(minimo.hint).toContain("sem taxa de servico");
    expect(minimo.hint).toContain("sem entrega");
  });

  it("a janela da tabela usa seletor com hora, nao texto", () => {
    const tabela = resources.find((r) => r.name === "tabelas-de-desconto");
    for (const nome of ["starts_at", "ends_at"]) {
      expect(tabela.formFields.find((f) => f.name === nome).type).toBe("datetime");
    }
  });
});
