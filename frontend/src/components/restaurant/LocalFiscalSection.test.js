import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PrimeVue from "primevue/config";

import LocalFiscalSection from "./LocalFiscalSection.vue";

/**
 * As duas travas da emissão local, na tela.
 *
 * Um terminal que liga isto passa a assinar NFC-e REAIS com o certificado da
 * empresa, e documento fiscal emitido não se apaga: só se cancela, um a um,
 * dentro do prazo. A conta autoriza E a loja liga — e a tela precisa mostrar
 * as duas, porque um interruptor que liga sem efeito é pior do que um
 * interruptor travado: o operador acha que ativou.
 */
function montar(config = {}, accountAllows = false) {
  return mount(LocalFiscalSection, {
    props: {
      config: {
        local_fiscal_enabled: false,
        local_fiscal_contingency: false,
        local_fiscal_url: "",
        ...config,
      },
      accountAllows,
    },
    global: { plugins: [PrimeVue] },
  });
}

describe("emissão local no cadastro fiscal", () => {
  it("explica a recusa quando a CONTA não autoriza", () => {
    const tela = montar({}, false);

    expect(tela.text()).toContain("Esta conta não autoriza emissão local");
  });

  it("some com o aviso quando a conta autoriza", () => {
    const tela = montar({}, true);

    expect(tela.text()).not.toContain("Esta conta não autoriza");
  });

  it("o endereço do Comunicador é editável com tudo ligado", () => {
    const tela = montar({ local_fiscal_enabled: true }, true);
    const campo = tela.find('[data-test="local-fiscal-url"]');

    expect(campo.attributes("disabled")).toBeUndefined();
  });

  it("o endereço fica travado enquanto a emissão local está desligada", () => {
    const tela = montar({ local_fiscal_enabled: false }, true);
    const campo = tela.find('[data-test="local-fiscal-url"]');

    expect(campo.attributes("disabled")).toBeDefined();
  });

  it("digitar o endereço avisa quem guarda o formulário", async () => {
    const tela = montar({ local_fiscal_enabled: true }, true);

    await tela.find('[data-test="local-fiscal-url"]').setValue("http://127.0.0.1:55555");

    const eventos = tela.emitted("update-field");
    expect(eventos.at(-1)).toEqual([
      "local_fiscal_url",
      "http://127.0.0.1:55555",
    ]);
  });

  it("mostra o endereço já gravado", () => {
    const tela = montar(
      { local_fiscal_enabled: true, local_fiscal_url: "http://127.0.0.1:8090" },
      true,
    );

    expect(tela.find('[data-test="local-fiscal-url"]').element.value).toBe(
      "http://127.0.0.1:8090",
    );
  });
});
