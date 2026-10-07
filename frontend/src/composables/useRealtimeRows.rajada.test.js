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

import { BURST_LIMIT, useRealtimeRows } from "./useRealtimeRows";

describe("rajada de eventos (importação em massa)", () => {
  it("acima do limite para de buscar linha a linha e relê uma vez no fim", async () => {
    vi.useFakeTimers();
    handlers.length = 0;
    const onBurst = vi.fn();
    const estado = {
      rows: ref([]), total: ref(0), page: ref(1), rowsPerPage: ref(20), ordering: ref(""), filterCount: ref(0),
    };
    const service = { retrieve: vi.fn().mockResolvedValue({ id: "x" }) };
    let api;
    mount(defineComponent({
      setup() {
        api = useRealtimeRows({ resource: "menu.product", service, onBurst, ...estado });
        return () => h("div");
      },
    }));

    for (let i = 0; i < 60; i += 1) await api.apply({ action: "created", id: `p${i}` });
    const buscas = service.retrieve.mock.calls.length;
    vi.advanceTimersByTime(1000);

    expect(buscas).toBeLessThanOrEqual(BURST_LIMIT);
    expect(onBurst).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
