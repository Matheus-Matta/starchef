import { mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import { describe, expect, it } from "vitest";

import FilterField from "./FilterField.vue";

// Os filtros usavam <select> nativo e caixa de texto até para campo com
// valores conhecidos. Agora: sempre o componente do PrimeVue do tipo.

// O Calendar consulta `matchMedia`, que o jsdom não tem.
window.matchMedia ||= () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
const montar = (props) => mount(FilterField, { props, global: { plugins: [PrimeVue] }, attrs: { fluid: true } });

describe("FilterField", () => {
  it("campo com valores conhecidos é uma lista do PrimeVue, que ocupa a largura toda", () => {
    const campo = montar({ field: { name: "status", label: "Situação" }, opcoes: [{ label: "Pago", value: "paid" }] });

    expect(campo.find(".p-dropdown").exists()).toBe(true);
    expect(campo.find("select").exists()).toBe(false);
    // A regra global de `fluid` (primevue-tokens.css) depende do atributo chegar à raiz.
    expect(campo.find(".p-dropdown").attributes()).toHaveProperty("fluid");
  });

  it("sim/não são três botões fixos, e o valor volta como texto", async () => {
    const campo = montar({ field: { name: "is_active", label: "Ativo", type: "boolean" } });

    const botoes = campo.findAll(".p-selectbutton .p-button");
    expect(botoes.map((botao) => botao.text())).toEqual(["Todos", "Sim", "Não"]);
    await botoes[1].trigger("click");
    expect(campo.emitted("update:modelValue").at(-1)).toEqual(["true"]);
  });

  it("número e data usam InputNumber e Calendar, não caixa de texto", () => {
    expect(montar({ field: { name: "total", type: "money" } }).find(".p-inputnumber").exists()).toBe(true);
    expect(montar({ field: { name: "issued", type: "date" } }).find(".p-calendar").exists()).toBe(true);
  });
});
