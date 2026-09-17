import { createPinia, setActivePinia } from "pinia";
import PrimeVue from "primevue/config";
import ToastService from "primevue/toastservice";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../services/api";
import { useAuthStore } from "../stores/auth";
import CashRegisterView from "./CashRegisterView.vue";

vi.mock("../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const DialogStub = {
  props: ["visible", "header"],
  emits: ["update:visible"],
  template: '<div v-if="visible" class="dialog-stub"><h2>{{ header }}</h2><slot /></div>',
};

const station = {
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
    id: "session-1",
    status: "open",
    operator: "Ana",
    opened_by: "operator-1",
    opened_terminal_label: "Computador antigo",
    opened_at: "2026-09-17T10:00:00Z",
  },
};

function mockLoads() {
  api.get.mockImplementation((url) => {
    if (url === "/cash-stations/") return Promise.resolve({ data: [station] });
    if (url === "/cash-register/current/") return Promise.resolve({ data: null });
    return Promise.resolve({ data: [] });
  });
}

function mountView(profileType) {
  setActivePinia(createPinia());
  useAuthStore().user = { id: "admin-1", profile_type: profileType };
  return mount(CashRegisterView, {
    global: {
      plugins: [PrimeVue, ToastService],
      stubs: { Dialog: DialogStub },
    },
  });
}

describe("CashRegisterView - liberacao administrativa", () => {
  beforeEach(() => {
    api.get.mockReset();
    api.post.mockReset();
    mockLoads();
  });

  it("esconde a acao de um gerente", async () => {
    const wrapper = mountView("manager");
    await flushPromises();

    expect(wrapper.text()).not.toContain("Forçar liberação");
  });

  it("permite ao admin justificar e liberar a sessao", async () => {
    api.post.mockResolvedValue({ data: { ...station.current_session, status: "cancelled" } });
    const wrapper = mountView("admin");
    await flushPromises();

    const forceButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Forçar liberação");
    await forceButton.trigger("click");
    await wrapper.get("#force-release-reason").setValue("O computador antigo quebrou.");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Liberar caixa")
      .trigger("click");
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith(
      "/cash-register/session-1/force-release/",
      { reason: "O computador antigo quebrou." },
    );
  });
});
