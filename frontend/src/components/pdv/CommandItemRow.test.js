import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CommandItemRow from "./CommandItemRow.vue";

/**
 * No histórico, VENDA e PERDA são coisas diferentes.
 *
 * A linha comparava o estado com `"closed"`, um valor que o modelo não usa
 * mais: item cobrado e item cancelado apareciam os dois como "aberto", e quem
 * conferia uma reclamação não distinguia o que foi pago do que foi jogado
 * fora.
 */
function montar(item, props = {}) {
  return mount(CommandItemRow, { props: { item, ...props } });
}

const BASE = { id: "1", product_name: "Coxinha", quantity: 2, total_price: "12.00" };

describe("CommandItemRow", () => {
  it("item cobrado aparece como cobrado", () => {
    const tela = montar({ ...BASE, command_status: "billed" }, { mostrarEstado: true });

    expect(tela.text()).toContain("cobrado");
  });

  it("item cancelado aparece como cancelado, com o motivo", () => {
    // O motivo é o que responde "por que sumiu da conta?" sem abrir relatório.
    const tela = montar(
      { ...BASE, command_status: "cancelled", void_reason: "cliente desistiu" },
      { mostrarEstado: true },
    );

    expect(tela.text()).toContain("cancelado");
    expect(tela.text()).toContain("cliente desistiu");
  });

  it("cancelado sem motivo nao inventa um", () => {
    const tela = montar({ ...BASE, command_status: "cancelled" }, { mostrarEstado: true });

    expect(tela.text()).toContain("cancelado");
    expect(tela.text()).not.toContain("—");
  });

  it("item pendente aparece como aberto", () => {
    const tela = montar({ ...BASE, command_status: "pending" }, { mostrarEstado: true });

    expect(tela.text()).toContain("aberto");
  });

  it("sem mostrarEstado a linha nao fala de estado nenhum", () => {
    // É o caso do grupo aberto: ali todo item está aberto, e repetir isso em
    // cada linha só rouba espaço do que importa.
    const tela = montar({ ...BASE, command_status: "pending" });

    expect(tela.text()).not.toContain("aberto");
  });

  it("produto por quilo mostra o peso, nao a contagem", () => {
    const tela = montar({ ...BASE, quantity: 0.325 });

    expect(tela.text()).toContain("0.325 kg");
  });
});
