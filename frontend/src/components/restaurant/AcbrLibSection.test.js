import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PrimeVue from "primevue/config";

import AcbrLibSection from "./AcbrLibSection.vue";

/**
 * A contingência offline do emissor ACBrLib, na tela.
 *
 * Ela só existe para NFC-e: numa NF-e o interruptor ligado enganaria o
 * operador, que acharia a loja coberta sem estar.
 */
function montar(config) {
  return mount(AcbrLibSection, { props: { config }, global: { plugins: [PrimeVue] } });
}

describe("AcbrLibSection", () => {
  it("liga e desliga a contingência offline da NFC-e", async () => {
    const tela = montar({ document_model: "65", offline_contingency: false });
    await tela.find('[data-test="acbr-offline-contingency"] input').setValue(true);
    expect(tela.emitted("update-field")[0]).toEqual(["offline_contingency", true]);
  });

  it("na NF-e o interruptor fica travado e explica por quê", () => {
    const tela = montar({ document_model: "55", offline_contingency: true });
    expect(tela.find('[data-test="acbr-only-nfce"]').exists()).toBe(true);
    expect(tela.text()).toContain("Desligada");
  });
});
