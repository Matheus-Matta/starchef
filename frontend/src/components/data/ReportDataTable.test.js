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

  // 25 linhas em 3 páginas: o maior valor está na ÚLTIMA. Ordenar do maior
  // para o menor tem de trazê-lo para a primeira linha da primeira página.
  it("ordenar decrescente traz o maior de todas as linhas, não só da página", async () => {
    const rows = Array.from({ length: 25 }, (_, i) => ({ name: `P${i + 1}`, total: String(i + 1) }));
    const tabela = mount(ReportDataTable, {
      props: { rows, columns: [{ key: "name", label: "Produto" }, { key: "total", label: "Total", type: "number" }] },
      global: { plugins: [PrimeVue] },
    });
    const titulo = tabela.findAll("th").find((th) => th.text().includes("Total"));

    await titulo.trigger("click");
    await titulo.trigger("click");

    expect(tabela.find("tbody tr").text()).toContain("P25");
  });

  // O dinheiro chega do servidor como TEXTO ("50.00"). Ordenado como texto,
  // "100.00" vinha antes de "50.00" e a sobra de caixa negativa ia parar no
  // meio da lista.
  it("dinheiro ordena pelo valor, não pelo texto, inclusive negativo", async () => {
    const rows = ["9.90", "-5.00", "100.00", "50.00", "1000.00"].map((v, i) => ({ name: `C${i}`, total: v }));
    const tabela = mount(ReportDataTable, {
      props: { rows, columns: [{ key: "name", label: "Caixa" }, { key: "total", label: "Diferença", type: "money" }] },
      global: { plugins: [PrimeVue] },
    });
    const titulo = tabela.findAll("th").find((th) => th.text().includes("Diferença"));

    await titulo.trigger("click");

    const emReais = tabela
      .findAll("tbody tr")
      .map((tr) => Number(tr.findAll("td")[1].text().replace(/[^\d,-]/g, "").replace(",", ".")));
    expect(emReais).toEqual([-5, 9.9, 50, 100, 1000]);
  });

  it("avisa quando o servidor mandou menos linhas do que existem", () => {
    const tabela = mount(ReportDataTable, {
      props: { rows: [{ name: "A" }], columns: [{ key: "name", label: "Nome" }], total: 1500 },
      global: { plugins: [PrimeVue] },
    });

    expect(tabela.text()).toContain("Mostrando 1 de 1.500");
  });

  it("lista completa não mostra aviso nenhum", () => {
    const tabela = mount(ReportDataTable, {
      props: { rows: [{ name: "A" }], columns: [{ key: "name", label: "Nome" }], total: 1 },
      global: { plugins: [PrimeVue] },
    });

    expect(tabela.text()).not.toContain("Mostrando");
  });
});
