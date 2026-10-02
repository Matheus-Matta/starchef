import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import ConfirmationService from "primevue/confirmationservice";
import ToastService from "primevue/toastservice";
import Tooltip from "primevue/tooltip";
import { describe, expect, it, vi } from "vitest";

const chamadas = [];
vi.mock("../../services/api", () => ({
  api: {
    post: async (...args) => (chamadas.push(args), {
      data: {
        reset: [{ id: "c1", number: 11, items_removed: 2 }],
        skipped: [{ id: "c2", number: 14, reason: "Está na conta #88, que continua aberta." }],
      },
    }),
  },
}));

const { default: CommandBulkResetDialog } = await import("./CommandBulkResetDialog.vue");
const { resumoDoZeramento } = await import("./commandResetSummary");

function montar(props) {
  return mount(CommandBulkResetDialog, {
    props: { visible: true, ...props },
    global: {
      plugins: [PrimeVue, ToastService, ConfirmationService],
      directives: { tooltip: Tooltip },
      stubs: { Dialog: { template: "<div><slot /><slot name=\"footer\" /></div>" } },
    },
  });
}

const confirmar = async (tela) => {
  const botoes = tela.findAll("button");
  await botoes[botoes.length - 1].trigger("click");
  await flushPromises();
};

describe("zerar comandas", () => {
  it("manda as comandas sem repetir, com o motivo, para o endpoint de zerar — não o de excluir", async () => {
    const tela = montar({ selection: [{ id: "c1" }, { id: "c2" }, { id: "c1" }] });

    await tela.find("textarea").setValue("Fim do expediente");
    await confirmar(tela);

    expect(chamadas.at(-1)[0]).toBe("/commands/bulk-reset/");
    expect(chamadas.at(-1)[1]).toMatchObject({ ids: ["c1", "c2"], reason: "Fim do expediente" });
    expect(tela.emitted("completed")).toBeTruthy();
  });

  it("sem motivo não chama o servidor", async () => {
    const antes = chamadas.length;
    const tela = montar({ selection: [{ id: "c1" }] });

    await confirmar(tela);

    expect(chamadas.length).toBe(antes);
    expect(tela.emitted("completed")).toBeFalsy();
  });

  it("o resumo diz qual comanda ficou e por quê", () => {
    const aviso = resumoDoZeramento(
      [{ number: 11, items_removed: 2 }, { number: 12, items_removed: 1 }],
      [{ number: 14, reason: "Está na conta #88, que continua aberta." }],
    );

    expect(aviso.severity).toBe("warn");
    expect(aviso.summary).toBe("2 comanda(s) zerada(s), 3 item(ns) retirado(s)");
    expect(aviso.detail).toContain("comanda 14 (Está na conta #88");
  });
});
