import { createPinia, setActivePinia } from "pinia";
import PrimeVue from "primevue/config";
import ToastService from "primevue/toastservice";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../services/api";
import { useAuthStore } from "../stores/auth";
import CashRegisterView from "./CashRegisterView.vue";

vi.mock("../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  loginRequest: vi.fn(),
  temporaryAuthenticatedPost: vi.fn(),
  closeTemporarySession: vi.fn(),
}));

// O Dialog real do PrimeVue teletransporta para `document.body` e depende de
// transições — nada disso é o que este teste quer provar. O stub mantém só o
// contrato que o `v-model:visible` da tela usa, e deixa o comportamento (quais
// botões aparecem, o que cada um dispara) inteiramente por conta do
// CashRegisterView de verdade.
const DialogStub = {
  props: ["visible", "header"],
  emits: ["update:visible"],
  template: '<div v-if="visible" class="dialog-stub"><h2>{{ header }}</h2><slot /></div>',
};

const openStation = {
  id: "station-1",
  name: "Caixa Principal",
  code: "CX-01",
  restaurant: "rest-1",
  operators: [],
  operator_names: ["Ana"],
  cash_limit: "0.00",
  is_active: true,
  recent_sessions: [],
  current_session: {
    id: "sessao-1",
    status: "open",
    operator: "Ana",
    opened_by: 5,
    opened_terminal_label: "Caixa Principal",
    opened_at: "2026-08-30T10:00:00Z",
    actual_amount: null,
    difference_amount: null,
  },
};

const pendingStation = {
  ...openStation,
  id: "station-2",
  name: "Caixa Secundário",
  current_session: {
    ...openStation.current_session,
    id: "sessao-2",
    status: "pending_manager_approval",
    pending_operation: "closing",
    actual_amount: "980.00",
    difference_amount: "-20.00",
  },
};

/** Encadeia as 4 chamadas que `load()` faz no `onMounted`, na ordem do código-fonte. */
function mockLoad(stations) {
  api.get
    .mockResolvedValueOnce({ data: stations })
    .mockResolvedValueOnce({ data: [] })
    .mockResolvedValueOnce({ data: [] })
    .mockResolvedValueOnce({ data: null });
}

function mountView() {
  setActivePinia(createPinia());
  useAuthStore().user = { id: 5, profile_type: "manager" };
  return mount(CashRegisterView, {
    global: {
      plugins: [PrimeVue, ToastService],
      stubs: { Dialog: DialogStub },
    },
  });
}

/**
 * O botão "Editar caixa" precisa mostrar a situação REAL da sessão e dar um
 * jeito de resolvê-la contra o servidor — sem que isso dependa do PDV ter
 * conseguido entregar o fechamento. Antes, "Editar caixa" só abria o cadastro
 * do caixa (nome/código/operadores): um caixa preso não tinha, ali, nenhum
 * indício do problema nem uma saída.
 */
describe("CashRegisterView — edição de caixa mostra e resolve a sessão", () => {
  beforeEach(() => {
    api.get.mockReset();
    api.post.mockReset();
  });

  afterEach(() => vi.restoreAllMocks());

  it("mostra o resumo da sessão na hora, antes do detalhe completo chegar", async () => {
    mockLoad([openStation]);
    const wrapper = mountView();
    await flushPromises();

    // A busca do detalhe fica pendente de propósito, para provar que o
    // resumo já sincronizado na lista aparece sem esperar a rede.
    let resolveDetail;
    api.get.mockReturnValueOnce(new Promise((resolve) => { resolveDetail = resolve; }));

    await wrapper.get('[aria-label="Editar caixa"]').trigger("click");
    await flushPromises();

    expect(wrapper.get("h2").text()).toBe("Editar caixa");
    expect(wrapper.text()).toContain("Sessão aberta, sem pendências.");
    expect(wrapper.text()).toContain("Resolva por aqui");
    expect(wrapper.text()).toContain("sem depender do terminal PDV");

    resolveDetail({ data: { ...openStation.current_session, expected_amount: "150.00" } });
    await flushPromises();
    // O texto continua correto depois que o detalhe completo chega.
    expect(wrapper.text()).toContain("Sessão aberta, sem pendências.");
  });

  it('"Fechar caixa agora" abre o fechamento direto contra o servidor', async () => {
    mockLoad([openStation]);
    const wrapper = mountView();
    await flushPromises();
    api.get.mockResolvedValueOnce({ data: openStation.current_session });

    await wrapper.get('[aria-label="Editar caixa"]').trigger("click");
    await flushPromises();

    const closeButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Fechar caixa agora"));
    expect(closeButton).toBeTruthy();

    await closeButton.trigger("click");

    // O diálogo de edição fecha e o de fechamento assume, já apontando para a
    // sessão certa — sem passar por `selectStation`/navegação nenhuma.
    const headers = wrapper.findAll("h2").map((node) => node.text());
    expect(headers).toContain("Fechar Caixa Principal");
    expect(headers).not.toContain("Editar caixa");
  });

  it('sessão com divergência oferece "Aprovar e concluir", não "Fechar caixa agora"', async () => {
    mockLoad([pendingStation]);
    const wrapper = mountView();
    await flushPromises();
    api.get.mockResolvedValueOnce({
      data: { ...pendingStation.current_session, expected_amount: "1000.00", notes: "" },
    });

    await wrapper.get('[aria-label="Editar caixa"]').trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Divergência no fechamento");
    expect(wrapper.text()).toContain("requer aprovação gerencial");
    expect(wrapper.text()).toContain("Diferença");

    const buttonLabels = wrapper.findAll("button").map((button) => button.text());
    expect(buttonLabels).toContain("Aprovar e concluir");
    expect(buttonLabels).not.toContain("Fechar caixa agora");

    const approveButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Aprovar e concluir");
    await approveButton.trigger("click");

    const headers = wrapper.findAll("h2").map((node) => node.text());
    expect(headers).toContain("Resolver divergência do fechamento");
  });

  it('"Transferir sessão" abre a transferência com a sessão em edição', async () => {
    mockLoad([openStation]);
    const wrapper = mountView();
    await flushPromises();
    api.get.mockResolvedValueOnce({ data: openStation.current_session });

    await wrapper.get('[aria-label="Editar caixa"]').trigger("click");
    await flushPromises();

    const transferButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Transferir sessão"));
    await transferButton.trigger("click");

    const headers = wrapper.findAll("h2").map((node) => node.text());
    expect(headers).toContain("Transferir sessão de caixa");
  });

  it("uma sessão que não foi encontrada no detalhe mantém o resumo da lista", async () => {
    // Ex.: a sessão foi resolvida por outra aba entre a lista carregar e o
    // clique em editar. Sem o resumo como reserva, o gerente veria o
    // diálogo de edição sem NENHUMA informação sobre o que estava acontecendo.
    mockLoad([openStation]);
    const wrapper = mountView();
    await flushPromises();
    api.get.mockRejectedValueOnce({ response: { status: 404 } });

    await wrapper.get('[aria-label="Editar caixa"]').trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Sessão aberta, sem pendências.");
  });

  it("um caixa sem sessão ativa não mostra o bloco de resolução", async () => {
    mockLoad([{ ...openStation, current_session: null }]);
    const wrapper = mountView();
    await flushPromises();

    await wrapper.get('[aria-label="Editar caixa"]').trigger("click");
    await flushPromises();

    expect(wrapper.text()).not.toContain("Resolva por aqui");
    expect(wrapper.text()).not.toContain("Fechar caixa agora");
  });
});
