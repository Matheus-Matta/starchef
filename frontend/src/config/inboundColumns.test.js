import { describe, expect, it } from "vitest";

import { resources } from "./resources";

// A chave de acesso (44 dígitos) ocupava metade da tabela de notas de
// entrada. Ela fica no detalhe da nota, com botão de copiar, e a busca da
// lista continua achando a nota por ela (`search_fields` no backend).
describe("tabela de notas de entrada", () => {
  it("não mostra a chave de acesso", () => {
    const notas = resources.find((r) => r.endpoint === "/inbound-nfe/");
    expect(notas.columns.map((c) => c.key)).not.toContain("access_key");
  });

  it("a lista de pedidos mostra as comandas dos itens", () => {
    const pedidos = resources.find((r) => r.endpoint === "/orders/");
    expect(pedidos.columns.map((c) => c.key)).toContain("command_label");
  });
});
