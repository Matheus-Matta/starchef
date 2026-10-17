import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import DanfePrintQuestion from "./DanfePrintQuestion.vue";

let wrapper;
afterEach(() => wrapper?.unmount());

const tecla = (key) => window.dispatchEvent(new KeyboardEvent("keydown", { key }));

describe("DanfePrintQuestion", () => {
  it("ENTER imprime e ESC cancela", () => {
    wrapper = mount(DanfePrintQuestion, { props: { summary: "Pedido #7 · NFC-e 12" } });
    expect(wrapper.text()).toContain("Imprimir a NFC-e?");
    tecla("Enter");
    tecla("Escape");
    expect(wrapper.emitted("print")).toHaveLength(1);
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });

  it("clicar fora do modal ou em Cancelar cancela", async () => {
    wrapper = mount(DanfePrintQuestion, { props: { summary: "Pedido #7" } });
    await wrapper.find(".danfe-question__overlay").trigger("click");
    await wrapper.findAll("button").find((b) => b.text().startsWith("Cancelar")).trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(2);
    expect(wrapper.emitted("print")).toBeUndefined();
  });

  it("fechado, o ENTER do PDV não é capturado", () => {
    wrapper = mount(DanfePrintQuestion, { props: { summary: "" } });
    tecla("Enter");
    expect(wrapper.find(".danfe-question__overlay").exists()).toBe(false);
    expect(wrapper.emitted("print")).toBeUndefined();
  });
});
