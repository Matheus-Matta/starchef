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

    expect(r).toEqual({ created: 1, updated: 3, errors: [], warnings: [] });
    expect(api.chamadas).toEqual([
      ["update", "p1", "prd-5cfaf4"],
      ["update", "p9", "PRD-ZZ"],
      ["create", "PRD-NOVO"],
      ["update", "novo-PRD-NOVO", "PRD-NOVO"],
    ]);
  });

  it("relação aceita id ou nome, e id que sumiu vira aviso sem derrubar a linha", async () => {
    // O CSV real: o perfil cad479a8 foi apagado e recriado com outro id, e as
    // oito bebidas que apontavam para ele davam "Pk inválido".
    const api = servico([{ id: "p1", internal_code: "PRD-73772D" }]);
    const cadastros = {
      "/fiscal/profiles/": [{ id: "novo-id", name: "REFRIGERANTE_VIDRO_ST" }],
      "/restaurants/": [{ id: "r1", trade_name: "Cobogó" }],
    };
    const relacoes = [
      ...campos,
      { name: "fiscal_profile", label: "Perfil fiscal", type: "remote-dropdown", endpoint: "/fiscal/profiles/", optionLabel: "name" },
      { name: "restaurants", label: "Restaurantes", type: "remote-multiselect", endpoint: "/restaurants/", optionLabel: "trade_name" },
    ];
    const payloads = [
      { internal_code: "PRD-73772D", fiscal_profile: "cad479a8-8608-4a56-a890-ed9d365075d1", restaurants: ["r1"] },
      { internal_code: "PRD-NOVO", fiscal_profile: "refrigerante_vidro_st", restaurants: ["Cobogó", "Filial X"] },
    ];

    const r = await importUpsert({
      service: api,
      fields: relacoes,
      payloads,
      servicoPara: (campo) => ({ list: async () => ({ results: cadastros[campo.endpoint], next: null }) }),
    });

    expect(r.errors).toEqual([]);
    expect(r.created + r.updated).toBe(2);
    expect(payloads[0]).not.toHaveProperty("fiscal_profile");
    expect(payloads[1]).toMatchObject({ fiscal_profile: "novo-id", restaurants: ["r1"] });
    expect(r.warnings).toEqual([
      'Linha 2: Perfil fiscal "cad479a8-8608-4a56-a890-ed9d365075d1" não existe — mantido o valor atual.',
      'Linha 3: Restaurantes "Filial X" não existe — mantido o valor atual.',
    ]);
  });
});
