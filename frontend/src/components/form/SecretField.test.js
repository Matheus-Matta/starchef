import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import SecretField from "./SecretField.vue";

// Os componentes PrimeVue leem `$primevue` (injetado pelo plugin `PrimeVue`)
// mesmo fora de tema/estilo — sem isso o render quebra com "Cannot read
// properties of undefined (reading 'config')".
function mountField(props) {
  return mount(SecretField, { props, global: { plugins: [PrimeVue] } });
}

/**
 * Um `<Password>` com valor vazio e só um placeholder mascarado é
 * indistinguível de um campo realmente vazio — o placeholder some ao focar.
 * O componente resolve isso mostrando a máscara como VALOR de verdade
 * (bloqueado, com o selo "Salvo") enquanto o operador não pede para trocar.
 */
describe("SecretField", () => {
  it("mostra a máscara bloqueada, com o selo Salvo, quando já está configurado", () => {
    const wrapper = mountField({ modelValue: "", configured: true, revealing: false });

    const masked = wrapper.find("input[disabled]");
    expect(masked.exists()).toBe(true);
    expect(masked.element.value).toBe("••••••••");
    expect(wrapper.text()).toContain("Salvo");
    expect(wrapper.text()).toContain("Alterar");
  });

  it("nunca expõe o valor real dentro do campo mascarado", () => {
    // O valor real não deveria nem chegar a este ponto (o backend nunca
    // devolve segredo), mas o teste garante que, mesmo que chegasse, o
    // componente não o renderiza — só a máscara fixa.
    const wrapper = mountField({ modelValue: "segredo-super-secreto", configured: true, revealing: false });

    expect(wrapper.html()).not.toContain("segredo-super-secreto");
  });

  it("mostra o campo editável quando ainda não há valor salvo", () => {
    const wrapper = mountField({ modelValue: "", configured: false, revealing: false });

    expect(wrapper.find("input[disabled]").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Salvo");
  });

  it("mostra o campo editável quando o operador pediu para alterar", () => {
    const wrapper = mountField({ modelValue: "", configured: true, revealing: true });

    expect(wrapper.find("input[disabled]").exists()).toBe(false);
  });

  it('emite "edit" ao clicar em Alterar, sem tocar no valor', async () => {
    const wrapper = mountField({ modelValue: "", configured: true, revealing: false });

    await wrapper.get("button").trigger("click");

    expect(wrapper.emitted("edit")).toHaveLength(1);
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("sempre mostra o aviso de segurança", () => {
    const configured = mountField({ configured: true });
    const empty = mountField({ configured: false });

    for (const wrapper of [configured, empty]) {
      expect(wrapper.text()).toContain("não pode ser exibido novamente");
    }
  });
});
