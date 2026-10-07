import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { describe, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../services/api", () => ({ api: { get } }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import StockPositionView from "./StockPositionView.vue";

// O relatório de estoque mostra código e fornecedor, e manda os filtros ao
// servidor (que sabe quais produtos consomem cada insumo).
describe("StockPositionView", () => {
  it("mostra código e fornecedor e filtra no servidor", async () => {
    get.mockImplementation((url) => {
      if (url === "/stock/positions/") {
        return Promise.resolve({ data: { positions: [{
          ingredient_id: "i1", ingredient_name: "Coca lata", code: "BEB-01", supplier_name: "Ambev",
          unit: "un", balance: "10.000", situation: "ok", locations: [], average_cost: "3.12", stock_value: "31.20",
          is_active: true,
        }], totals: {} } });
      }
      return Promise.resolve({ data: { results: [] } });
    });
    const tela = mount(StockPositionView, { global: { plugins: [PrimeVue] } });
    await flushPromises();

    expect(tela.text()).toContain("BEB-01");
    expect(tela.text()).toContain("Ambev");

    tela.vm.supplierId = "s1";
    tela.vm.categoryId = "c1";
    await tela.vm.load();
    const chamada = get.mock.calls.filter(([url]) => url === "/stock/positions/").at(-1);
    expect(chamada[1].params).toEqual({ supplier: "s1", category: "c1" });
  });
});
