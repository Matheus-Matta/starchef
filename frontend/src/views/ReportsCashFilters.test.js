import { ref } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReportsView from "./ReportsView.vue";
import { api } from "../services/api";
import { reportService } from "../services/reportService";

vi.mock("primevue/chart", () => ({ default: { template: "<div />" } }));
vi.mock("../services/api", () => ({ api: { get: vi.fn() }, API_BASE_URL: "/api/v1" }));
vi.mock("../services/reportService", () => ({
  endpoints: { cash: "/reports/cash-movements/" },
  reportService: { get: vi.fn() },
}));
vi.mock("../composables/useRealtimeResource", () => ({ useRealtimeResource: vi.fn() }));

describe("ReportsView - filtros do relatório de caixa", () => {
  beforeEach(() => {
    api.get.mockReset();
    reportService.get.mockReset();
    api.get.mockImplementation((url) => Promise.resolve({
      data: url === "/cash-stations/"
        ? [{ id: "cash-1", name: "Caixa Principal", code: "CX01" }]
        : [],
    }));
    reportService.get.mockResolvedValue({ summary: {}, sessions: [], movements: [] });
  });

  it("lista os caixas e envia o caixa escolhido ao relatório", async () => {
    const wrapper = mount(ReportsView, {
      props: { section: "cash" },
      global: {
        provide: { theme: ref("light") },
        stubs: {
          AppDateRange: { template: "<div />" },
          CashMovementsReport: { template: "<div />" },
        },
      },
    });
    await flushPromises();

    const select = wrapper.get('select[aria-label="Caixa"]');
    expect(select.text()).toContain("Caixa Principal · CX01");
    await select.setValue("cash-1");
    await flushPromises();

    expect(reportService.get).toHaveBeenLastCalledWith("cash", expect.objectContaining({
      cash_station: "cash-1",
    }));
  });
});
