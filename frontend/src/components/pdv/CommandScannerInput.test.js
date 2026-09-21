import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CommandScannerInput from "./CommandScannerInput.vue";

describe("CommandScannerInput", () => {
  it("limpa o campo apos cada leitura — a proxima comanda vem logo atras", async () => {
    const wrapper = mount(CommandScannerInput, { attachTo: document.body });
    const input = wrapper.get("input");

    await input.setValue("CMD-0013");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.emitted("scan")[0]).toEqual(["CMD-0013"]);
    expect(input.element.value).toBe("");
    wrapper.unmount();
  });

  it("devolve o foco ao campo — senao a segunda leitura vai para lugar nenhum", async () => {
    const wrapper = mount(CommandScannerInput, { attachTo: document.body });
    const input = wrapper.get("input");

    await input.setValue("CMD-0014");
    await wrapper.get("form").trigger("submit");
    await wrapper.vm.$nextTick();

    expect(document.activeElement).toBe(input.element);
    wrapper.unmount();
  });

  it("nao emite nada com o campo em branco", async () => {
    const wrapper = mount(CommandScannerInput);

    await wrapper.get("input").setValue("   ");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.emitted("scan")).toBeUndefined();
    wrapper.unmount();
  });
});
