import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InboundRestaurantSelector from "./InboundRestaurantSelector.vue";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({ api: { get: vi.fn() } }));

describe("seletor de unidade das notas recebidas", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lista os restaurantes e permite escolher sem usar a sidebar", async () => {
    api.get.mockResolvedValue({
      data: { results: [
        { id: "restaurante-a", trade_name: "Unidade A" },
        { id: "restaurante-b", trade_name: "Unidade B" },
      ] },
    });
    const wrapper = mount(InboundRestaurantSelector, { props: { modelValue: "" } });
    await flushPromises();

    await wrapper.get("select").setValue("restaurante-b");

    expect(api.get).toHaveBeenCalledWith("/restaurants/", expect.objectContaining({ skipRestaurantScope: true }));
    expect(wrapper.emitted("update:modelValue").at(-1)).toEqual(["restaurante-b"]);
  });

  it("mantém o nome acessível quando usado no cabeçalho compacto", async () => {
    api.get.mockResolvedValue({ data: { results: [] } });
    const wrapper = mount(InboundRestaurantSelector, { props: { modelValue: "", compact: true } });
    await flushPromises();

    expect(wrapper.get("label").classes()).toContain("inbound-unit--compact");
    expect(wrapper.get("label span").text()).toBe("Unidade para consultar a SEFAZ");
    expect(wrapper.text()).not.toContain("Escolha aqui a unidade");
  });
});
