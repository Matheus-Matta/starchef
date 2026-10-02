import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SalesDiscrepancyList from "../components/cash/SalesDiscrepancyList.vue";
import CashDiscrepancyReportView from "./CashDiscrepancyReportView.vue";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), query: { sessoes: "s1,s2" } }));
vi.mock("vue-router", () => ({
  useRoute: () => ({ query: mocks.query }),
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
}));
vi.mock("../services/api", () => ({ api: { get: mocks.get, post: mocks.post } }));
vi.mock("../stores/auth", () => ({ useAuthStore: () => ({ user: { profile_type: "manager" } }) }));

const PIX = { payment_method: "pix", name: "PIX" };
const REPORT = {
  totals: {
    registered_sales: "15000.00", discrepancy_total: "3500.00", received_total: "18500.00", open_count: 1,
    registered_by_method: [{ ...PIX, amount: "9000.00" }, { payment_method: "card", name: "Cartão", amount: "6000.00" }],
    discrepancy_by_method: [{ ...PIX, amount: "3500.00" }],
  },
  sessions: [{
    cash_register: "s1", cash_station_name: "Caixa 01", operator_name: "João", drawer_difference: "0.00",
    registered_sales: "15000.00", discrepancy_total: "3500.00", received_total: "18500.00",
    registered_by_method: [], discrepancy_by_method: [],
    discrepancies: [{ id: "d1", amount: "3500.00", status: "open", reason: "Movimento alto", payment_methods: [{ ...PIX, amount: "3500.00" }] }],
  }],
};

const stubs = {
  ReportDataTable: { props: ["rows"], template: "<div class='rows'>{{ rows.map((r) => `${r.name}:${r.registered}+${r.discrepancy}=${r.received}`).join('|') }}</div>" },
  SalesDiscrepancyDialog: true,
  Dialog: { props: ["visible"], template: "<div v-if='visible'><slot /></div>" },
};

describe("CashDiscrepancyReportView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.query = { sessoes: "s1,s2" };
    mocks.get.mockResolvedValue({ data: REPORT });
  });

  it("pede as sessões selecionadas e cruza vendas e divergência por forma", async () => {
    const wrapper = mount(CashDiscrepancyReportView, { global: { plugins: [PrimeVue], stubs } });
    await flushPromises();

    expect(mocks.get).toHaveBeenCalledWith("/cash-discrepancy-report/", { params: { cash_registers: "s1,s2" } });
    expect(wrapper.text()).toContain("2 sessões selecionadas");
    expect(wrapper.text()).toContain("18.500,00");
    // A mesma forma nas duas listas vira UMA linha: 9000 + 3500 = 12500.
    expect(wrapper.find(".rows").text()).toBe("PIX:9000+3500=12500|Cartão:6000+0=6000");
    expect(wrapper.text()).toContain("Movimento alto");
  });

  it("sem sessão selecionada explica em vez de chamar a API", async () => {
    mocks.query = {};
    const wrapper = mount(CashDiscrepancyReportView, { global: { plugins: [PrimeVue], stubs } });
    await flushPromises();

    expect(mocks.get).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Selecione ao menos uma sessão");
  });

  it("erro do servidor vira recado", async () => {
    mocks.get.mockRejectedValue({ response: { status: 400, data: { error: { message: "Selecione de 1 a 100 sessões de caixa." } } } });
    const wrapper = mount(CashDiscrepancyReportView, { global: { plugins: [PrimeVue], stubs } });
    await flushPromises();

    expect(wrapper.text()).toMatch(/Selecione de 1 a 100|erro|Erro/);
  });
});

describe("SalesDiscrepancyList", () => {
  const item = { id: "d1", amount: "10.00", status: "open", reason: "x", payment_methods: [] };
  const montar = () => mount(SalesDiscrepancyList, { props: { items: [item] }, global: { plugins: [PrimeVue], stubs } });

  it("regularizar exige a descrição e manda para a rota certa", async () => {
    mocks.post.mockResolvedValue({ data: { ...item, status: "regularized" } });
    const wrapper = montar();
    await wrapper.findAll("button").find((b) => b.text() === "Registrar regularização").trigger("click");
    const confirmar = () => wrapper.findAll("button").filter((b) => b.text() === "Registrar regularização").at(-1);
    expect(confirmar().attributes("disabled")).toBeDefined();

    await wrapper.find("#discrepancy-decision-text").setValue("Protocolo 123");
    await confirmar().trigger("click");
    await flushPromises();

    expect(mocks.post).toHaveBeenCalledWith("/cash-discrepancies/d1/regularize/", { note: "Protocolo 123" });
    expect(wrapper.emitted("changed")[0][0].status).toBe("regularized");
  });

  it("409 (outro gerente decidiu antes) recarrega a lista", async () => {
    mocks.post.mockRejectedValue({ response: { status: 409, data: { error: { message: "A divergência está regularizada: nada a fazer." } } } });
    const wrapper = montar();
    await wrapper.findAll("button").find((b) => b.text() === "Marcar como analisada").trigger("click");
    await wrapper.findAll("button").filter((b) => b.text() === "Marcar como analisada").at(-1).trigger("click");
    await flushPromises();

    expect(wrapper.emitted("changed")).toEqual([[null]]);
  });

  it("sem permissão de decidir não mostra os botões", () => {
    const wrapper = mount(SalesDiscrepancyList, { props: { items: [item], canDecide: false }, global: { plugins: [PrimeVue], stubs } });

    expect(wrapper.findAll("button")).toHaveLength(0);
  });
});
