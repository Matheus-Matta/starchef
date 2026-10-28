import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import ToastService from "primevue/toastservice";
import { describe, expect, it, vi } from "vitest";

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../services/api", () => ({ api: { get, post } }));

import StockBulkAdjustView from "./StockBulkAdjustView.vue";

// O ajuste em lote vai num pedido só, com o motivo e cada linha.
describe("StockBulkAdjustView", () => {
  it("manda produtos e insumos no mesmo lote e limpa a tela no sucesso", async () => {
    get.mockResolvedValue({ data: { results: [{ id: "loc-1", name: "Depósito" }] } });
    post.mockResolvedValue({ data: { created: 2 } });
    const tela = mount(StockBulkAdjustView, { global: { plugins: [PrimeVue, ToastService] } });
    await flushPromises();

    tela.vm.adicionar({ value: { id: "p1", name: "Refrigerante", stock_unit: "UN" } }, "product");
    tela.vm.adicionar({ value: { id: "i1", name: "Arroz", unit: "kg" } }, "ingredient");
    tela.vm.linhas[0].quantity = 7;
    tela.vm.linhas[1].mode = "out";
    tela.vm.linhas[1].quantity = 1.5;
    tela.vm.motivo = "Inventário";
    await tela.vm.salvar();

    expect(post).toHaveBeenCalledWith("/stock/movements/bulk-adjust/", {
      location: "loc-1",
      reason: "Inventário",
      items: [
        { product: "p1", mode: "set", quantity: "7" },
        { ingredient: "i1", mode: "out", quantity: "1.5" },
      ],
    });
    expect(tela.vm.linhas).toHaveLength(0);
  });

  it("busca somente o tipo de produto selecionado", async () => {
    get.mockResolvedValue({ data: { results: [{ id: "loc-1", name: "Depósito" }] } });
    const tela = mount(StockBulkAdjustView, { global: { plugins: [PrimeVue, ToastService] } });
    await flushPromises();
    get.mockResolvedValueOnce({ data: { results: [] } });

    tela.vm.tipoSelecionado = "REUSABLE_MATERIAL";
    await tela.vm.buscarItens({ query: "garrafa" });

    expect(get).toHaveBeenLastCalledWith("/menu/products/", {
      params: { search: "garrafa", is_active: true, item_type: "REUSABLE_MATERIAL", page_size: 20 },
    });
  });
});
