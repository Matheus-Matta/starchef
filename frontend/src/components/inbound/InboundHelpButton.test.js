import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import InboundHelpButton from "./InboundHelpButton.vue";

describe("ajuda da consulta de notas na SEFAZ", () => {
  it("mostra a explicação apenas quando o usuário abre a ajuda", async () => {
    const wrapper = mount(InboundHelpButton, {
      props: { description: "A rotina automática consulta a SEFAZ a cada 5 horas." },
      attrs: { class: "rpro__help-action" },
      global: { stubs: { Dialog: { template: '<div v-if="visible" role="dialog"><slot /></div>', props: ["visible"] } } },
    });

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
    expect(wrapper.get("button").classes()).toContain("rpro__help-action");
    await wrapper.get('button[aria-label="Ajuda sobre a consulta SEFAZ"]').trigger("click");
    expect(wrapper.get('[role="dialog"]').text()).toContain("A rotina automática consulta a SEFAZ");
  });
});
