import { mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { describe, expect, it } from "vitest";

import ProductCostsReport from "./ProductCostsReport.vue";

describe("ProductCostsReport", () => {
  it("mostra vendido, custo, margem e de onde veio o custo", () => {
    const tela = mount(ProductCostsReport, {
      props: {
        report: {
          totals: { revenue: "74.00", cost: "23.50", margin: "50.50" },
          by_product: [
            { product_id: "p1", code: "XB", product_name: "X-Burger", quantity: "2", revenue: "50.00",
              cost: "16.00", margin: "34.00", margin_percent: "68.00", cost_source: "baixa" },
            { product_id: "p2", code: "SU", product_name: "Suco", quantity: "3", revenue: "24.00",
              cost: "7.50", margin: "16.50", margin_percent: "68.75", cost_source: "cadastro" },
          ],
        },
      },
      global: { plugins: [PrimeVue] },
    });
    const texto = tela.text();
    expect(texto).toContain("50,50");
    expect(texto).toContain("68,2% do vendido");
    expect(texto).toContain("X-Burger");
    expect(texto).toContain("Cadastro (estimado)");
  });
});
