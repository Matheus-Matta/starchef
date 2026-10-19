import { mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { describe, expect, it } from "vitest";

import { duracao } from "../../utils/duracao";
import CommandsReport from "./CommandsReport.vue";

const relatorio = {
  now: { registered: 40, in_use: 3, free: 37, in_open_bill: 1, in_use_total: "182.40", in_use_items: 9 },
  open_commands: [
    { id: "a", number: 12, customer_name: "Marina", table: "5", items: 4, total: "98.00",
      open_since: "2026-10-18T19:00:00-03:00", last_launch: "2026-10-18T20:10:00-03:00", in_open_bill: true },
    { id: "b", number: 7, customer_name: "", table: "", items: 5, total: "84.40",
      open_since: "2026-10-18T20:30:00-03:00", last_launch: "2026-10-18T20:45:00-03:00", in_open_bill: false },
  ],
  period: { paid: 58, paid_total: "4321.50", average_ticket: "74.51", used: 61, launched_items: 412,
            launched_total: "4500.00", lost_items: 3, lost_total: "45.00",
            average_items_per_paid: "6.90", average_stay_minutes: 85.4 },
  by_command: [{ number: 12, uses: 4, items: 20, total: "380.00", last_use: "2026-10-18T18:00:00-03:00" }],
};

const montar = (report) => mount(CommandsReport, { props: { report }, global: { plugins: [PrimeVue] } });

describe("CommandsReport", () => {
  it("mostra o salão agora: em uso, livres, valor a receber e presas em conta aberta", () => {
    const texto = montar(relatorio).text();

    expect(texto).toContain("Em uso agora");
    expect(texto).toContain("de 40 cadastradas");
    expect(texto).toMatch(/R\$\s182,40/);
    expect(texto).toContain("Presas em conta aberta");
  });

  it("mostra o período: pagas, ticket médio, usadas, permanência e perdas", () => {
    const texto = montar(relatorio).text();

    expect(texto).toMatch(/R\$\s74,51/);
    expect(texto).toContain("1 h 25 min");
    expect(texto).toMatch(/R\$\s45,00/);
    expect(texto).toContain("61");
  });

  it("a comanda presa numa conta aberta aparece sinalizada na lista", () => {
    const linhas = montar(relatorio).findAll("tbody tr");

    expect(linhas[0].text()).toContain("12");
    expect(linhas[0].text()).toContain("Em conta aberta");
    expect(linhas[1].text()).toContain("Anotando");
  });

  // "45 min" e "1 h" ordenados como TEXTO invertiam a fila: a comanda aberta
  // há uma hora aparecia como mais recente que a de 45 minutos.
  it("ordenar por 'Aberta há' segue o tempo, não o texto", async () => {
    const agora = Date.now();
    const ha = (min) => new Date(agora - min * 60000).toISOString();
    const tela = montar({
      ...relatorio,
      open_commands: [
        { id: "1", number: 1, items: 1, total: "10.00", open_since: ha(60), in_open_bill: false },
        { id: "2", number: 2, items: 1, total: "10.00", open_since: ha(45), in_open_bill: false },
        { id: "3", number: 3, items: 1, total: "10.00", open_since: ha(130), in_open_bill: false },
      ],
    });
    const titulo = tela.findAll("th").find((th) => th.text().includes("Aberta há"));

    await titulo.trigger("click");

    const ordem = tela.findAll("tbody")[0].findAll("tr").map((tr) => tr.findAll("td")[0].text());
    expect(ordem).toEqual(["2", "1", "3"]);
  });

  it("relatório ainda carregando (vazio) não quebra a tela", () => {
    const texto = montar({}).text();

    expect(texto).toContain("Em uso agora");
    expect(texto).toContain("—");
  });

  it.each([
    [null, "—"],
    [0.4, "menos de 1 min"],
    [45, "45 min"],
    [60, "1 h"],
    [85.4, "1 h 25 min"],
    [1500, "25 h"],
  ])("duração de %s minutos vira %s", (minutos, esperado) => {
    expect(duracao(minutos)).toBe(esperado);
  });
});
