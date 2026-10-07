import { describe, expect, it } from "vitest";

import { applyRealtimeChange, listIsAtRest, matchesFixedParams } from "./realtimeRows";

// A lista recebe a mudança pelo WebSocket e mexe só na linha — antes ela
// refazia o GET da página inteira a cada item novo, e ainda voltava para a
// página 1 de quem estava na 3.
const linha = (id, extra = {}) => ({ id, ...extra });
const pagina = (n) => Array.from({ length: n }, (_, i) => linha(`p${i}`));

describe("listIsAtRest", () => {
  it("só a página 1, sem filtro e na ordem padrão, recebe o tempo real", () => {
    expect(listIsAtRest({ page: 1, filterCount: 0, ordering: "" })).toBe(true);
  });

  it("filtro ativo, outra página ou ordenação escolhida: não mexe", () => {
    expect(listIsAtRest({ page: 1, filterCount: 1, ordering: "" })).toBe(false);
    expect(listIsAtRest({ page: 2, filterCount: 0, ordering: "" })).toBe(false);
    expect(listIsAtRest({ page: 1, filterCount: 0, ordering: "name" })).toBe(false);
  });
});

describe("applyRealtimeChange", () => {
  it("item novo entra no topo e o último sai, para a página continuar com 20", () => {
    const rows = pagina(20);
    const result = applyRealtimeChange({ rows, total: 57, pageSize: 20, action: "created", record: linha("novo") });

    expect(result.rows).toHaveLength(20);
    expect(result.rows[0].id).toBe("novo");
    expect(result.rows.at(-1).id).toBe("p18");
    expect(result.total).toBe(58);
  });

  it("página com espaço só ganha a linha", () => {
    const result = applyRealtimeChange({ rows: pagina(3), total: 3, pageSize: 20, action: "created", record: linha("novo") });
    expect(result.rows.map((r) => r.id)).toEqual(["novo", "p0", "p1", "p2"]);
  });

  it("o mesmo item duas vezes não duplica: vira atualização no lugar", () => {
    const rows = [linha("a", { total: 1 }), linha("b")];
    const result = applyRealtimeChange({ rows, total: 2, pageSize: 20, action: "created", record: linha("a", { total: 9 }) });

    expect(result.rows.map((r) => r.id)).toEqual(["a", "b"]);
    expect(result.rows[0].total).toBe(9);
    expect(result.total).toBe(2);
  });

  it("atualização troca a linha no lugar, sem mudar a ordem", () => {
    const rows = [linha("a"), linha("b", { status: "open" }), linha("c")];
    const result = applyRealtimeChange({ rows, total: 3, pageSize: 20, action: "updated", record: linha("b", { status: "paid" }) });

    expect(result.rows.map((r) => r.id)).toEqual(["a", "b", "c"]);
    expect(result.rows[1].status).toBe("paid");
  });

  it("atualização de quem não está na página entra no topo (foi mexido agora)", () => {
    const result = applyRealtimeChange({ rows: pagina(2), total: 2, pageSize: 20, action: "updated", record: linha("x") });
    expect(result.rows[0].id).toBe("x");
    expect(result.total).toBe(3);
  });

  it("lista por nome não puxa para o topo um alterado que não está na página", () => {
    const rows = pagina(2);
    const result = applyRealtimeChange({ rows, total: 2, pageSize: 20, action: "updated", record: linha("x"), recencyOrdered: false });
    expect(result.rows).toBe(rows);
  });

  it("exclusão tira a linha e baixa o total", () => {
    const result = applyRealtimeChange({ rows: [linha("a"), linha("b")], total: 30, pageSize: 20, action: "deleted", id: "a" });
    expect(result.rows.map((r) => r.id)).toEqual(["b"]);
    expect(result.total).toBe(29);
  });

  it("registro que saiu do recorte da tela é retirado, não atualizado", () => {
    const result = applyRealtimeChange({ rows: [linha("a"), linha("b")], total: 2, pageSize: 20, action: "updated", id: "a", record: null });
    expect(result.rows.map((r) => r.id)).toEqual(["b"]);
  });
});

describe("matchesFixedParams", () => {
  it("a tela de pedidos abertos não recebe o pedido que foi pago", () => {
    expect(matchesFixedParams({ status: "paid" }, { status: "open" })).toBe(false);
    expect(matchesFixedParams({ status: "open" }, { status: "open" })).toBe(true);
  });

  it("parâmetro que não é campo do registro não decide nada", () => {
    expect(matchesFixedParams({ status: "open" }, { page_size: 50, include: "x" })).toBe(true);
  });
});
