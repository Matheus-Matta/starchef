import { mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { describe, expect, it } from "vitest";

import ReportDataTable from "./ReportDataTable.vue";

// Nome comprido de produto pulava linha e esticava a tabela: a célula corta
// com reticências, e o texto inteiro fica no mouse.
describe("ReportDataTable", () => {
  it("cada celula traz o valor inteiro no title", () => {
    const tabela = mount(ReportDataTable, {
      props: {
        rows: [{ name: "Picanha na chapa com fritas, arroz, farofa e vinagrete", total: "1234.5" }],
        columns: [{ key: "name", label: "Produto" }, { key: "total", label: "Total", type: "money", align: "right" }],
      },
      global: { plugins: [PrimeVue] },
    });

    const celulas = tabela.findAll(".report-data-table__cell");
    expect(celulas[0].attributes("title")).toBe("Picanha na chapa com fritas, arroz, farofa e vinagrete");
    expect(celulas[1].attributes("title")).toContain("1.234,50");
  });
});
