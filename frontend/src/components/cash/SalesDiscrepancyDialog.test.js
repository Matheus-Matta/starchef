import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SalesDiscrepancyDialog from "./SalesDiscrepancyDialog.vue";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../../services/api", () => ({ api: { get: mocks.get, post: mocks.post } }));

const METHODS = [
  { id: "pix", name: "PIX" },
  { id: "card", name: "Cartão" },
];

function montar() {
  return mount(SalesDiscrepancyDialog, {
    props: { visible: true, cashRegister: "sessao-1" },
    global: {
      plugins: [PrimeVue],
      stubs: {
        Dialog: { template: "<div><slot /></div>" },
        InputNumber: {
          props: ["modelValue", "inputId"],
          emits: ["update:modelValue"],
          template: `<input :id="inputId" @input="$emit('update:modelValue', Number($event.target.value))" />`,
        },
      },
    },
  });
}

const botao = (wrapper, texto) => wrapper.findAll("button").find((b) => b.text().includes(texto));

describe("SalesDiscrepancyDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue({ data: { results: METHODS } });
  });

  it("só libera o registro com valor e motivo, e manda o corpo certo", async () => {
    mocks.post.mockResolvedValue({ data: { id: "d1", amount: "2000.50" } });
    const wrapper = montar();
    await flushPromises();
    expect(botao(wrapper, "Registrar divergência").attributes("disabled")).toBeDefined();

    await wrapper.find("#discrepancy-pix").setValue("2000.5");
    expect(botao(wrapper, "Registrar divergência").attributes("disabled")).toBeDefined();
    await wrapper.find("#discrepancy-reason").setValue("Movimento alto");
    expect(wrapper.text()).toContain("2.000,50");
    await botao(wrapper, "Registrar divergência").trigger("click");
    await flushPromises();

    expect(mocks.post).toHaveBeenCalledWith("/cash-discrepancies/", {
      cash_register: "sessao-1",
      reason: "Movimento alto",
      notes: "",
      by_payment_method: [{ payment_method: "pix", amount: "2000.50" }],
    });
    expect(wrapper.emitted("saved")[0][0]).toEqual({ id: "d1", amount: "2000.50" });
    expect(wrapper.emitted("update:visible").at(-1)).toEqual([false]);
  });

  it("recusa do servidor vira recado e o diálogo continua aberto", async () => {
    mocks.post.mockRejectedValue({ response: { status: 400, data: { error: { message: "Forma de pagamento não encontrada." } } } });
    const wrapper = montar();
    await flushPromises();
    await wrapper.find("#discrepancy-card").setValue("10");
    await wrapper.find("#discrepancy-reason").setValue("x");
    await botao(wrapper, "Registrar divergência").trigger("click");
    await flushPromises();

    expect(wrapper.emitted("saved")).toBeUndefined();
    expect(wrapper.emitted("update:visible")).toBeUndefined();
    expect(wrapper.text()).toMatch(/não encontrada|erro|Erro/);
  });

  it("falha ao carregar as formas vira recado, sem quebrar a tela", async () => {
    mocks.get.mockRejectedValue(new Error("rede caiu"));
    const wrapper = montar();
    await flushPromises();

    expect(wrapper.find("#discrepancy-pix").exists()).toBe(false);
    expect(botao(wrapper, "Registrar divergência").attributes("disabled")).toBeDefined();
  });
});
