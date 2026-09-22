import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import DraftCartLine from "./DraftCartLine.vue";

/**
 * Numa conta com quatro comandas, o carrinho é uma lista só.
 *
 * Sem dizer de qual cartão é cada linha, ninguém sabe o que pertence a quem —
 * e a conferência em voz alta com o cliente ("quanto é a minha?") não fecha.
 */
const NOVO = { _id: "l1", product_name: "Coxinha", quantity: 2, unit_price: "6.00" };
const DE_COMANDA = { ...NOVO, _id: "c1", command_number: 12 };

describe("DraftCartLine", () => {
  it("item de comanda diz de QUAL comanda é", () => {
    const tela = mount(DraftCartLine, { props: { item: DE_COMANDA } });

    expect(tela.text()).toContain("Comanda 12");
  });

  it("item passado agora nao ganha selo de comanda", () => {
    const tela = mount(DraftCartLine, { props: { item: NOVO } });

    expect(tela.text()).not.toContain("Comanda");
  });

  it("item de comanda NAO tem o X", () => {
    // Ele não pertence a este carrinho: é consumo que já existe no cartão.
    // Um X aqui daria a impressão de apagar o consumo — e o caminho certo é
    // retirar a comanda inteira, no modal.
    const tela = mount(DraftCartLine, { props: { item: DE_COMANDA } });

    expect(tela.find(".linha__remover--vazio").exists()).toBe(true);
    expect(tela.findAll("button").some((b) => b.text() === "✕")).toBe(false);
  });

  it("item passado agora TEM o X", () => {
    const tela = mount(DraftCartLine, { props: { item: NOVO } });

    expect(tela.findAll("button").some((b) => b.text() === "✕")).toBe(true);
  });

  it("remover o item novo avisa quem montou a tela", async () => {
    const tela = mount(DraftCartLine, { props: { item: NOVO } });

    await tela.findAll("button").find((b) => b.text() === "✕").trigger("click");

    expect(tela.emitted("remove")).toBeTruthy();
  });
});
