import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../services/api";
import PdvCommandsView from "./PdvCommandsView.vue";

vi.mock("../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("../services/commandService", () => ({
  findCommandByCode: vi.fn(),
  fetchCommandItems: vi.fn(),
  printCommandReceipt: vi.fn(),
}));

const routerStub = { push: vi.fn() };
vi.mock("vue-router", () => ({ useRouter: () => routerStub }));

function montar() {
  return mount(PdvCommandsView, {
    global: { stubs: { CommandItemsPanel: true, CommandScannerInput: true } },
  });
}

describe("a tela de comandas sempre sai do carregando", () => {
  beforeEach(() => vi.clearAllMocks());

  it("mostra os cartoes quando a lista chega paginada", async () => {
    api.get.mockResolvedValue({
      data: { count: 1, results: [{ id: "c1", number: 13, code: "C013", status: "free" }] },
    });

    const tela = montar();
    await flushPromises();

    expect(tela.text()).not.toContain("Carregando…");
    expect(tela.text()).toContain("13");
  });

  it("mostra os cartoes quando a lista chega como array puro", async () => {
    // Uma rota sem paginação devolve a lista direta. Ler só `results` faria a
    // tela ficar eternamente vazia sem nenhum erro para explicar por quê.
    api.get.mockResolvedValue({
      data: [{ id: "c1", number: 7, code: "C007", status: "occupied" }],
    });

    const tela = montar();
    await flushPromises();

    expect(tela.text()).toContain("7");
  });

  it("uma falha de rede vira recado na tela, nunca carregando para sempre", async () => {
    // O caso que o operador relatou: a tela ficava girando sem dizer nada. Um
    // spinner eterno é o pior formato de erro — não há o que tentar de novo,
    // porque parece que ainda está vindo.
    api.get.mockRejectedValue(new Error("Network Error"));

    const tela = montar();
    await flushPromises();

    expect(tela.text()).not.toContain("Carregando…");
    expect(tela.text()).toContain("Não foi possível carregar as comandas.");
  });

  it("um erro sem corpo da API tambem termina o carregamento", async () => {
    // `exc.response.data.detail` não existe num 502 do proxy nem num timeout:
    // ler essa cadeia sem defesa lançaria DENTRO do `catch`, e aí nem o
    // `finally` bastaria para a tela voltar ao normal.
    api.get.mockRejectedValue({ response: { status: 502 } });

    const tela = montar();
    await flushPromises();

    expect(tela.text()).not.toContain("Carregando…");
    expect(tela.text()).toContain("Não foi possível carregar as comandas.");
  });
});
