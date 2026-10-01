import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import ConfirmationService from "primevue/confirmationservice";
import ToastService from "primevue/toastservice";
import Tooltip from "primevue/tooltip";
import { describe, expect, it, vi } from "vitest";

const chamadas = [];
vi.mock("../../services/api", () => ({
  api: {
    post: async (...args) => (chamadas.push(args), { data: { cancelled: 2, deleted: 1, skipped: [] } }),
  },
}));

const { default: OrderBulkCancelDialog } = await import("./OrderBulkCancelDialog.vue");
const { default: OrderBulkDeleteDialog } = await import("./OrderBulkDeleteDialog.vue");

function montar(componente, props) {
  return mount(componente, {
    props: { visible: true, ...props },
    global: {
      plugins: [PrimeVue, ToastService, ConfirmationService],
      directives: { tooltip: Tooltip },
      // O Dialog real teleporta para o body; aqui basta o conteúdo.
      stubs: { Dialog: { template: "<div><slot /><slot name=\"footer\" /></div>" } },
    },
  });
}

const confirmar = async (tela) => {
  const botoes = tela.findAll("button");
  await botoes[botoes.length - 1].trigger("click");
  await flushPromises();
};

describe("ações em massa de pedidos", () => {
  it("na lista de notas cancela pelo PEDIDO de cada nota, sem repetir", async () => {
    // Duas notas do mesmo pedido viram UM cancelamento: o pedido leva a nota junto.
    const tela = montar(OrderBulkCancelDialog, {
      selection: [{ id: "n1", order: "p1" }, { id: "n2", order: "p1" }, { id: "n3", order: "p2" }],
      idField: "order",
      label: "Cancelar pedidos e notas",
    });

    await tela.find("textarea").setValue("Fechamento errado");
    await confirmar(tela);

    expect(chamadas.at(-1)[0]).toBe("/orders/bulk-cancel/");
    expect(chamadas.at(-1)[1]).toMatchObject({ ids: ["p1", "p2"], reason: "Fechamento errado" });
    expect(tela.emitted("completed")).toBeTruthy();
    expect(tela.emitted("update:visible").at(-1)).toEqual([false]);
  });

  it("sem motivo mostra o erro no campo e não chama o servidor", async () => {
    const antes = chamadas.length;
    const tela = montar(OrderBulkCancelDialog, { selection: [{ id: "p1" }] });

    await confirmar(tela);

    expect(chamadas.length).toBe(antes);
    expect(tela.text()).toContain("Informe o motivo do cancelamento.");
  });

  it("excluir manda os pedidos selecionados para a exclusão com trava", async () => {
    const tela = montar(OrderBulkDeleteDialog, { selection: [{ id: "p1" }, { id: "p2" }] });

    expect(tela.text()).toContain("sem nota fiscal e sem pagamento recebido");
    await confirmar(tela);

    expect(chamadas.at(-1)).toEqual(["/orders/bulk-delete/", { ids: ["p1", "p2"] }, { skipRestaurantScope: true }]);
  });
});
