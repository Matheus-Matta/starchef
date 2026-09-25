import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PdvCouponField from "./PdvCouponField.vue";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({ api: { post: vi.fn() } }));

/**
 * O que estes testes fixam é a fronteira: o componente NÃO decide nada sobre o
 * cupom. Ele manda o código, e quem responde se vale — e por quanto — é o
 * servidor. Uma validação otimista aqui mostraria o desconto na tela para o
 * servidor recusar depois, com o cliente já tendo ouvido o valor menor.
 */
describe("PdvCouponField", () => {
  beforeEach(() => {
    api.post.mockReset();
  });

  const montar = (props = {}) =>
    mount(PdvCouponField, { props: { orderId: "pedido-1", ...props } });

  it("manda o código em maiúsculas e emite o pedido que o servidor devolveu", async () => {
    api.post.mockResolvedValue({ data: { id: "pedido-1", coupon_code: "NATAL10", total: "54.00" } });
    const wrapper = montar();

    await wrapper.get("input").setValue("natal10");
    await wrapper.get(".cupom__btn--aplicar").trigger("click");
    await wrapper.vm.$nextTick();

    expect(api.post).toHaveBeenCalledWith("/orders/pedido-1/apply-coupon/", { code: "NATAL10" });
    // O TOTAL vem do servidor, já recalculado: refazer a conta aqui faria a
    // tela mostrar um número e a venda cobrar outro.
    expect(wrapper.emitted("applied")[0][0].total).toBe("54.00");
  });

  it("a recusa do servidor aparece no CAMPO, e o pedido não é emitido", async () => {
    api.post.mockRejectedValue({
      response: { status: 422, data: { error: { code: "coupon_rejected", message: "Este CPF já usou este cupom." } } },
    });
    const wrapper = montar();

    await wrapper.get("input").setValue("USADO");
    await wrapper.get(".cupom__btn--aplicar").trigger("click");
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();

    // A frase é sobre o cupom, e quem precisa lê-la está olhando o campo que
    // acabou de digitar — não um toast que desaparece em cinco segundos.
    expect(wrapper.get(".cupom__erro").text()).toContain("já usou este cupom");
    expect(wrapper.emitted("applied")).toBeUndefined();
  });

  it("com cupom aplicado, oferece TROCAR e RETIRAR em vez de aplicar", () => {
    const wrapper = montar({ applied: "NATAL10", discount: 6 });

    expect(wrapper.get(".cupom__aplicado").text()).toContain("NATAL10");
    expect(wrapper.get(".cupom__aplicado-valor").text()).toContain("6,00");
    expect(wrapper.get(".cupom__btn--aplicar").text()).toBe("Trocar");
    expect(wrapper.find(".cupom__btn--retirar").exists()).toBe(true);
  });

  it("retirar manda código VAZIO — é o gesto que o servidor entende como remover", async () => {
    api.post.mockResolvedValue({ data: { id: "pedido-1", coupon_code: "", total: "60.00" } });
    const wrapper = montar({ applied: "NATAL10", discount: 6 });

    await wrapper.get(".cupom__btn--retirar").trigger("click");
    await wrapper.vm.$nextTick();

    expect(api.post).toHaveBeenCalledWith("/orders/pedido-1/apply-coupon/", { code: "" });
    expect(wrapper.get("input").element.value).toBe("");
  });

  it("o campo acompanha o pedido quando o recálculo derruba o cupom", async () => {
    const wrapper = montar({ applied: "ACIMA50", discount: 5 });
    expect(wrapper.get("input").element.value).toBe("ACIMA50");

    // O operador removeu itens e o pedido deixou de se qualificar: o código sai
    // da tela, ou ele leria um cupom que já não vale.
    await wrapper.setProps({ applied: "" });

    expect(wrapper.get("input").element.value).toBe("");
  });

  it("não chama o servidor com o campo vazio", async () => {
    const wrapper = montar();

    expect(wrapper.get(".cupom__btn--aplicar").attributes("disabled")).toBeDefined();
    await wrapper.get(".cupom__btn--aplicar").trigger("click");

    expect(api.post).not.toHaveBeenCalled();
  });
});
