import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { describe, expect, it, vi } from "vitest";

const { handlers } = vi.hoisted(() => ({ handlers: [] }));
vi.mock("../services/realtimeService", () => ({
  realtimeService: {
    connect: vi.fn(),
    subscribe: (_event, handler) => {
      handlers.push(handler);
      return () => {};
    },
    state: {},
    connected: {},
    lastEvent: {},
  },
}));

import { useRealtimeResource } from "./useRealtimeResource";

function montar(options) {
  const recebidos = [];
  mount(defineComponent({
    setup() {
      useRealtimeResource("orders.order", (payload) => recebidos.push(payload.id), options);
      return () => h("div");
    },
  }));
  return recebidos;
}

describe("useRealtimeResource", () => {
  it("sem debounce, dois pedidos no mesmo instante chegam os dois", () => {
    handlers.length = 0;
    const recebidos = montar({ debounce: 0 });

    handlers[0]({ resource: "orders.order", id: "a" });
    handlers[0]({ resource: "orders.order", id: "b" });

    expect(recebidos).toEqual(["a", "b"]);
  });

  it("com debounce, a rajada vira uma chamada só (o último)", () => {
    vi.useFakeTimers();
    handlers.length = 0;
    const recebidos = montar({ debounce: 100 });

    handlers[0]({ resource: "orders.order", id: "a" });
    handlers[0]({ resource: "orders.order", id: "b" });
    vi.advanceTimersByTime(150);

    expect(recebidos).toEqual(["b"]);
    vi.useRealTimers();
  });
});
