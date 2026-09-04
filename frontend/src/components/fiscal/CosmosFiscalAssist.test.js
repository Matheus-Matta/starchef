import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../services/api";
import CosmosFiscalAssist from "./CosmosFiscalAssist.vue";

vi.mock("../../services/api", () => ({ api: { get: vi.fn() } }));

describe("CosmosFiscalAssist", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    api.get.mockReset();
  });

  afterEach(() => vi.useRealTimers());

  it("consulta automaticamente pelo nome e emite os campos fiscais sugeridos", async () => {
    api.get
      .mockResolvedValueOnce({ data: { active: true, configured: true, ready: true } })
      .mockResolvedValueOnce({
        data: {
          matched_product: "REFEICAO PRONTA CONGELADA",
          ncm: "21069090",
          cest: "1709900",
          fields: { ncm: "21069090", cest: "1709900" },
          warning: "Revise antes de emitir.",
        },
      });

    const wrapper = mount(CosmosFiscalAssist, {
      props: { name: "Refeição pronta" },
      global: { plugins: [PrimeVue] },
    });
    await flushPromises();
    await vi.advanceTimersByTimeAsync(700);
    await flushPromises();

    expect(api.get).toHaveBeenNthCalledWith(
      2,
      "/fiscal/profiles/cosmos-suggest/",
      expect.objectContaining({ params: { query: "Refeição pronta" } }),
    );
    expect(wrapper.emitted("suggestion")[0][0].fields).toEqual({ ncm: "21069090", cest: "1709900" });
    expect(wrapper.text()).toContain("NCM sugerido: 21069090");
  });

  it("nao consulta produto quando a integracao da conta esta desativada", async () => {
    api.get.mockResolvedValueOnce({ data: { active: false, configured: true, ready: false } });

    const wrapper = mount(CosmosFiscalAssist, {
      props: { name: "Refeição pronta" },
      global: {
        plugins: [PrimeVue],
        stubs: { RouterLink: { template: "<a><slot /></a>" } },
      },
    });
    await flushPromises();
    await vi.advanceTimersByTimeAsync(700);

    expect(api.get).toHaveBeenCalledTimes(1);
    expect(wrapper.find(".cosmos-assist").exists()).toBe(false);
    expect(wrapper.text()).toBe("");
  });
});
