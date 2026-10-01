import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import ToastService from "primevue/toastservice";
import { describe, expect, it, vi } from "vitest";

const chamadas = [];
vi.mock("../../services/api", () => ({
  api: { post: async (...args) => (chamadas.push(args), { data: { cancelled: 2, skipped: [] } }) },
}));

const { default: OrderBulkCancelButton } = await import("./OrderBulkCancelButton.vue");

function montar(props) {
  return mount(OrderBulkCancelButton, {
    props,
    global: {
      plugins: [PrimeVue, ToastService],
      // O Dialog real teleporta para o body; aqui basta o conteúdo.
      stubs: { Dialog: { template: "<div><slot /><slot name=\"footer\" /></div>" } },
    },
  });
}

describe("cancelar pedidos em massa", () => {
  it("na lista de notas cancela pelo PEDIDO de cada nota, sem repetir", async () => {
    // Duas notas do mesmo pedido (uma rejeitada, outra reenviada) viram UM
    // cancelamento: o pedido é que leva a nota junto.
    const tela = montar({
      selection: [{ id: "n1", order: "p1" }, { id: "n2", order: "p1" }, { id: "n3", order: "p2" }],
      idField: "order",
      label: "Cancelar pedidos e notas",
    });

    expect(tela.text()).toContain("(2)");
    await tela.find("#bulk-cancel-reason").setValue("Fechamento errado");
    const botoes = tela.findAll("button");
    await botoes[botoes.length - 1].trigger("click");
    await flushPromises();

    expect(chamadas.at(-1)[0]).toBe("/orders/bulk-cancel/");
    expect(chamadas.at(-1)[1]).toMatchObject({ ids: ["p1", "p2"], reason: "Fechamento errado" });
    expect(tela.emitted("completed")).toBeTruthy();
  });

  it("sem motivo o botão de confirmar fica travado", () => {
    const tela = montar({ selection: [{ id: "p1" }] });
    const botoes = tela.findAll("button");

    expect(botoes[botoes.length - 1].attributes("disabled")).toBeDefined();
  });
});
