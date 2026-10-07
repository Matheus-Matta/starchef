import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { describe, expect, it, vi } from "vitest";

const { handlers } = vi.hoisted(() => ({ handlers: [] }));
vi.mock("../services/realtimeService", () => ({
  realtimeService: {
    connect: vi.fn(),
    subscribe: (_e, handler) => { handlers.push(handler); return () => {}; },
    state: {}, connected: {}, lastEvent: {},
  },
}));

import { useRealtimeRows } from "./useRealtimeRows";

function montar({ page = 1, filtros = 0, registro = { id: "novo", status: "open" } } = {}) {
  handlers.length = 0;
  const estado = {
    rows: ref([{ id: "a" }, { id: "b" }]), total: ref(2), page: ref(page),
    rowsPerPage: ref(2), ordering: ref(""), filterCount: ref(filtros),
  };
  const service = { retrieve: vi.fn().mockResolvedValue(registro), list: vi.fn() };
  let api;
  mount(defineComponent({
    setup() {
      api = useRealtimeRows({ resource: "orders.order", service, fixedParams: { status: "open" }, ...estado });
      return () => h("div");
    },
  }));
  return { ...estado, service, api };
}

describe("useRealtimeRows", () => {
  it("item novo: busca SÓ ele, entra no topo e o último sai; nunca relê a página", async () => {
    const t = montar();
    await t.api.apply({ resource: "orders.order", action: "created", id: "novo" });

    expect(t.service.retrieve).toHaveBeenCalledWith("novo");
    expect(t.service.list).not.toHaveBeenCalled();
    expect(t.rows.value.map((r) => r.id)).toEqual(["novo", "a"]);
    expect(t.total.value).toBe(3);
  });

  it("com filtro ativo ou fora da página 1 não faz nada (nem busca)", async () => {
    for (const t of [montar({ filtros: 1 }), montar({ page: 2 })]) {
      await t.api.apply({ resource: "orders.order", action: "created", id: "novo" });
      expect(t.service.retrieve).not.toHaveBeenCalled();
      expect(t.rows.value.map((r) => r.id)).toEqual(["a", "b"]);
    }
  });

  it("registro que não bate o recorte fixo da tela sai dela", async () => {
    const t = montar({ registro: { id: "a", status: "paid" } });
    await t.api.apply({ resource: "orders.order", action: "updated", id: "a" });

    expect(t.rows.value.map((r) => r.id)).toEqual(["b"]);
  });
});
