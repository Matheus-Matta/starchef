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

  it("pagina pelo servidor: Próxima pede a página 2", async () => {
    pedidos.length = 0;
    resposta = (params) => Promise.resolve({ data: { count: 120, results: Array.from({ length: 50 }, (_, i) => evento(i + (params.page - 1) * 50)) } });
    const tela = await montar();

    const proxima = tela.findAll("button").find((b) => b.text().includes("Próxima"));
    await proxima.trigger("click");
    await flushPromises();

    const historico = pedidos.filter((p) => p.url.endsWith("/history/"));
    expect(historico.at(-1).params).toMatchObject({ page: 2, page_size: 50 });
    expect(tela.text()).toContain("Página 2 de 3");
  });
});
