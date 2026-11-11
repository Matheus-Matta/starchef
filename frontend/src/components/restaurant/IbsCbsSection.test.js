import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PrimeVue from "primevue/config";

import IbsCbsSection from "./IbsCbsSection.vue";

/**
 * O interruptor do IBS/CBS na configuração fiscal da loja.
 *
 * Ele precisa chegar ao PATCH com o nome do campo do backend
 * (`ibs_cbs_enabled`): com outro nome a tela mostraria "Ligado" e a nota
 * continuaria saindo sem o grupo.
 */
function montar(config) {
  return mount(IbsCbsSection, { props: { config }, global: { plugins: [PrimeVue] } });
}

describe("IbsCbsSection", () => {
  it("liga o envio do IBS/CBS com o nome do campo do backend", async () => {
    const tela = montar({ crt: "3", ibs_cbs_enabled: false });
    await tela.find('[data-test="ibscbs-enabled"] input').setValue(true);
    expect(tela.emitted("update-field")[0]).toEqual(["ibs_cbs_enabled", true]);
  });

  it("no Simples avisa que em 2026 não é obrigatório", () => {
    expect(montar({ crt: "1" }).find('[data-test="ibscbs-simples"]').exists()).toBe(true);
    expect(montar({ crt: "3" }).find('[data-test="ibscbs-simples"]').exists()).toBe(false);
  });
});
