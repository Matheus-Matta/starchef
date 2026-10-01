import { describe, expect, it } from "vitest";

import { importKeyFor, importUpsert } from "./importUpsert";

function servico(existentes) {
  const chamadas = [];
  return {
    chamadas,
    list: async () => ({ results: existentes, next: existentes.length ? "pagina-2" : null }),
    listByUrl: async () => ({ results: [{ id: "p9", internal_code: "PRD-ZZ" }], next: null }),
    update: async (id, payload) => chamadas.push(["update", id, payload.internal_code]),
    create: async (payload) => {
      chamadas.push(["create", payload.internal_code]);
      return { id: `novo-${payload.internal_code}` };
    },
  };
}

const campos = [{ name: "name" }, { name: "internal_code" }, { name: "sale_price" }];

describe("importar CSV atualiza o que já existe", () => {
  it("prefere o código interno ao nome como chave", () => {
    expect(importKeyFor(campos)).toBe("internal_code");
    expect(importKeyFor([{ name: "name" }])).toBe("name");
  });

  it("reimportar a planilha exportada atualiza em vez de dar valor duplicado", async () => {
    // "0 de 17 itens importados": toda linha tentava CRIAR um produto que já existia.
    const api = servico([{ id: "p1", internal_code: "PRD-5CFAF4" }]);

    const r = await importUpsert({
      service: api,
      fields: campos,
      payloads: [
        { internal_code: "prd-5cfaf4", sale_price: 8 },
        { internal_code: "PRD-ZZ", sale_price: 9 },
        { internal_code: "PRD-NOVO", sale_price: 1 },
        { internal_code: "PRD-NOVO", sale_price: 2 },
      ],
    });

    expect(r).toEqual({ created: 1, updated: 3, errors: [] });
    expect(api.chamadas).toEqual([
      ["update", "p1", "prd-5cfaf4"],
      ["update", "p9", "PRD-ZZ"],
      ["create", "PRD-NOVO"],
      ["update", "novo-PRD-NOVO", "PRD-NOVO"],
    ]);
  });
});
