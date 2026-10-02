import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import ConfirmationService from "primevue/confirmationservice";
import ToastService from "primevue/toastservice";
import Tooltip from "primevue/tooltip";
import { describe, expect, it, vi } from "vitest";

// O teste decide quando e como cada envio termina.
const envios = [];
vi.mock("../../services/api", () => ({
  api: { post: (url, corpo) => new Promise((resolve, reject) => envios.push({ url, corpo, resolve, reject })) },
}));

const { default: CommandBulkResetDialog } = await import("./CommandBulkResetDialog.vue");

function montar() {
  return mount(CommandBulkResetDialog, {
    props: { visible: true, selection: [{ id: "c1" }, { id: "c2" }] },
    global: {
      plugins: [PrimeVue, ToastService, ConfirmationService],
      directives: { tooltip: Tooltip },
      stubs: { Dialog: { template: "<div><slot /><slot name=\"footer\" /></div>" } },
    },
  });
}

const botaoZerar = (tela) => tela.findAll("button").at(-1);

describe("zerar comandas com a rede falhando", () => {
  it("erro 400 do servidor: o diálogo fica aberto, com o motivo, e pode tentar de novo", async () => {
    envios.length = 0;
    const tela = montar();
    await tela.find("textarea").setValue("Fim do dia");
    await botaoZerar(tela).trigger("click");

    envios[0].reject({ response: { status: 400, data: { error: { code: "invalid", message: { ids: "Selecione de 1 a 500 comandas." } } } } });
    await flushPromises();

    expect(tela.emitted("completed")).toBeFalsy();
    expect(tela.emitted("update:visible")?.some(([v]) => v === false)).toBeFalsy();
    expect(tela.find("textarea").element.value).toBe("Fim do dia");
    await botaoZerar(tela).trigger("click");
    expect(envios).toHaveLength(2);
  });

  it("queda de rede: não fecha nem dá a operação por feita", async () => {
    envios.length = 0;
    const tela = montar();
    await tela.find("textarea").setValue("Fim do dia");
    await botaoZerar(tela).trigger("click");

    envios[0].reject(new Error("Network Error"));
    await flushPromises();

    expect(tela.emitted("completed")).toBeFalsy();
  });

  it("clique duplo enquanto o primeiro envio não voltou manda UM pedido", async () => {
    envios.length = 0;
    const tela = montar();
    await tela.find("textarea").setValue("Fim do dia");

    await botaoZerar(tela).trigger("click");
    await botaoZerar(tela).trigger("click");
    await botaoZerar(tela).trigger("click");

    expect(envios).toHaveLength(1);
    envios[0].resolve({ data: { reset: [], skipped: [] } });
    await flushPromises();
    expect(tela.emitted("completed")).toBeTruthy();
  });
});
