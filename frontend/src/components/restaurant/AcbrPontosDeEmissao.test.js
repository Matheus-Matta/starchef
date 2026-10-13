import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PrimeVue from "primevue/config";

import AcbrPontosDeEmissao from "./AcbrPontosDeEmissao.vue";

/**
 * Quem emite a nota com servidor de loja: só a loja, ou loja e nuvem.
 *
 * Ligado, a nuvem precisa de uma série só dela. A tela avisa antes do salvar
 * quando a série falta ou repete a da loja — repetir é número duplicado na SEFAZ.
 */
function montar(config) {
  return mount(AcbrPontosDeEmissao, { props: { config }, global: { plugins: [PrimeVue] } });
}

describe("AcbrPontosDeEmissao", () => {
  it("ligar sugere a série seguinte à da loja quando a da nuvem está vazia", async () => {
    const tela = montar({ series: 1, cloud_emission: false, cloud_series: null });
    await tela.find('[data-test="acbr-cloud-emission"] input').setValue(true);
    expect(tela.emitted("update-field")).toEqual([["cloud_emission", true], ["cloud_series", 2]]);
  });

  it("desligado não mostra a série da nuvem", () => {
    const tela = montar({ series: 1, cloud_emission: false });
    expect(tela.find('[data-test="acbr-cloud-series"]').exists()).toBe(false);
    expect(tela.text()).toContain("Só a loja");
  });

  it("avisa quando a série da nuvem repete a da loja", () => {
    const tela = montar({ series: 3, cloud_emission: true, cloud_series: 3 });
    expect(tela.find('[data-test="acbr-cloud-series-error"]').text()).toContain("diferente");
  });
});
