import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { describe, expect, it, vi } from "vitest";

let resposta;
const pedidos = [];
vi.mock("../services/api", () => ({
  api: {
    get: (url, config) => {
      pedidos.push({ url, params: config?.params });
      if (!url.endsWith("/history/")) return Promise.resolve({ data: { number: 31 } });
      return typeof resposta === "function" ? resposta(config?.params) : resposta;
    },
  },
}));
vi.mock("vue-router", () => ({ useRouter: () => ({ back: vi.fn() }) }));

const { default: CommandHistoryView } = await import("./CommandHistoryView.vue");

const evento = (i) => ({ at: `2026-10-02T10:${String(i % 60).padStart(2, "0")}:00Z`, kind: "launched", label: "Lançado", user: "Ana", operator_code: "", item: null, order: null, table: null, reason: "" });

async function montar() {
  const tela = mount(CommandHistoryView, { props: { id: "c1" }, global: { plugins: [PrimeVue] } });
  await flushPromises();
  return tela;
}

describe("histórico da comanda", () => {
  it("erro do servidor mostra a mensagem, sem tabela", async () => {
    resposta = Promise.reject({ response: { status: 500, data: { error: { code: "internal_error", message: "Ocorreu um erro interno." } } } });
    const tela = await montar();

    expect(tela.find("[role=alert]").text()).toContain("erro interno");
    expect(tela.find("table").exists()).toBe(false);
  });

  it("comanda sem nada no período mostra o estado vazio", async () => {
    resposta = Promise.resolve({ data: { count: 0, next: null, results: [] } });
    const tela = await montar();

    expect(tela.text()).toContain("Nada aconteceu com esta comanda no período");
  });

  it("filtro recusado pelo servidor (400) aparece como erro, não como lista vazia", async () => {
    resposta = (params) => (params?.after
      ? Promise.reject({ response: { status: 400, data: { error: { code: "invalid", message: { after: "Use uma data válida no formato AAAA-MM-DD." } } } } })
      : Promise.resolve({ data: { count: 1, results: [evento(1)] } }));
    const tela = await montar();

    await tela.findAll("input[type=date]")[0].setValue("2026-02-28");
    await tela.find("form").trigger("submit");
    await flushPromises();

    expect(tela.find("[role=alert]").text()).toContain("data válida");
  });

  it("carrega todo o histórico e o título em uma única requisição", async () => {
    pedidos.length = 0;
    resposta = Promise.resolve({ data: {
      count: 250,
      command: { id: "c1", number: 31 },
      results: Array.from({ length: 250 }, (_, i) => evento(i)),
    } });
    const tela = await montar();

    const historico = pedidos.filter((p) => p.url.endsWith("/history/"));
    expect(historico).toHaveLength(1);
    expect(historico[0].params).toEqual({ all: "1" });
    expect(pedidos).toHaveLength(1);
    expect(tela.text()).toContain("Comanda 31");
    expect(tela.findComponent({ name: "ReportDataTable" }).props("rows")).toHaveLength(250);
    expect(tela.find(".cmd-history__pager").exists()).toBe(false);
  });
});
