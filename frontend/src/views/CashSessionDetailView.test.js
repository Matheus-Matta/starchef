import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CashSessionDetailView from "./CashSessionDetailView.vue";

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  download: vi.fn(),
  print: vi.fn(),
  back: vi.fn(),
}));

vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { id: "session-1" } }),
  useRouter: () => ({ back: mocks.back }),
}));
vi.mock("../services/api", () => ({ api: { get: mocks.apiGet } }));
vi.mock("../services/cashSessionExport", () => ({
  downloadCashSessionCsv: mocks.download,
  printCashSessionStatement: mocks.print,
}));

const statement = {
  session: {
    id: "session-1", cash_station_name: "Caixa central", opened_by_name: "Ana", terminal_label: "Balcão 1",
    status: "closed_with_difference", opened_at: "2026-09-17T10:00:00Z", closed_at: "2026-09-17T18:00:00Z",
    opening_amount: "100.00", expected_amount: "180.00", actual_amount: "175.00", difference_amount: "-5.00",
    movements: [{ id: "m1", movement_type: "withdrawal", amount: "20.00", status: "cancelled", reason: "Falha no malote" }],
    sales: [{ id: "p1", order_sequence: 42, payment_method_name: "Dinheiro", amount: "80.00" }],
  },
  orders: [{ sequence: 42, reference: "Mesa 3", items: [{ id: "i1", product_name: "Prato executivo", quantity: 1, unit_price: "80.00", total_price: "80.00", status: "delivered", addons: [] }] }],
};

describe("CashSessionDetailView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.apiGet.mockResolvedValue({ data: statement });
  });

  it("carrega o extrato completo e oferece impressão e exportação", async () => {
    const wrapper = mount(CashSessionDetailView, {
      global: {
        plugins: [PrimeVue],
        stubs: {
          CashSessionSummary: { template: "<div>Resumo financeiro</div>" },
          ReportDataTable: { props: ["rows"], template: "<div>{{ rows.map((row) => row.product_name || row.reason || row.payment_method_name).join(' ') }}</div>" },
          CashMovementDetailsDialog: true,
        },
      },
    });
    await flushPromises();

    expect(mocks.apiGet).toHaveBeenCalledWith("/cash-register/session-1/statement/");
    expect(wrapper.text()).toContain("Caixa central");
    expect(wrapper.text()).toContain("Ocorrências e falhas");
    expect(wrapper.text()).toContain("Pedidos da sessão");
    expect(wrapper.text()).toContain("Prato executivo");
    await wrapper.findAll("button").find((button) => button.text().includes("Exportar CSV")).trigger("click");
    await wrapper.findAll("button").find((button) => button.text().includes("Imprimir")).trigger("click");
    expect(mocks.download).toHaveBeenCalledWith(statement);
    expect(mocks.print).toHaveBeenCalledWith(statement);
  });
});
