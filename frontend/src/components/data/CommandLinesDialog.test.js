import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import ConfirmationService from "primevue/confirmationservice";
import ToastService from "primevue/toastservice";
import Tooltip from "primevue/tooltip";
import { describe, expect, it, vi } from "vitest";

import { emOrdemDeImpressao, linhasDaApi, mover, rotuloDaLinha, tituloValido } from "./commandLines";

// As linhas que a comanda da Balança Rápida imprime abaixo do peso. O formato
// é o do backend (`Restaurant.linhas_da_comanda`); um tipo errado aqui seria
// recusado com 400 e o gerente perderia o que montou.

const chamadas = [];
vi.mock("../../services/browserPersistence", () => ({ getBrowserValue: () => "r1" }));
vi.mock("../../services/api", () => ({
  api: {
    get: async (url) => {
      chamadas.push(["get", url]);
      if (url === "/restaurants/r1/") {
        return { data: { linhas_da_comanda: [{ tipo: "branco" }, { tipo: "produto", produto: "p1" }] } };
      }
      return { data: { results: [{ id: "p1", name: "Água sem gás" }] } };
    },
    patch: async (url, corpo) => (chamadas.push(["patch", url, corpo]), { data: {} }),
  },
}));

const { default: CommandLinesDialog } = await import("./CommandLinesDialog.vue");

function montar() {
  return mount(CommandLinesDialog, {
    props: { visible: true },
    global: {
      plugins: [PrimeVue, ToastService, ConfirmationService],
      directives: { tooltip: Tooltip },
      stubs: { Dialog: { template: "<div><slot /><slot name=\"footer\" /></div>" } },
    },
  });
}

describe("linhas da comanda — regras", () => {
  it("em branco vai sempre para o fim, como sai no papel", () => {
    const linhas = emOrdemDeImpressao([{ tipo: "branco" }, { tipo: "texto", nome: "Coca-Cola" }]);
    expect(linhas.map((l) => l.tipo)).toEqual(["texto", "branco"]);
  });

  it("tipo desconhecido e título vazio da API são descartados", () => {
    expect(linhasDaApi([{ tipo: "bebida" }, { tipo: "texto", nome: "  " }, { tipo: "texto", nome: " Suco " }]))
      .toEqual([{ tipo: "texto", nome: "Suco" }]);
  });

  it("título: espaços somem; vazio ou acima de 40 caracteres é recusado", () => {
    expect(tituloValido("  Coca   Cola ")).toBe("Coca Cola");
    expect(tituloValido("   ")).toBeNull();
    expect(tituloValido("x".repeat(41))).toBeNull();
  });

  it("linha em branco não sai do fim ao mover", () => {
    const linhas = [{ tipo: "texto", nome: "A" }, { tipo: "branco" }];
    expect(mover(linhas, 0, 1)).toEqual(linhas);
  });

  it("produto que saiu do cardápio aparece avisando que não sai", () => {
    expect(rotuloDaLinha({ tipo: "produto", produto: "x" }, {})).toMatch(/não sai/);
  });
});

describe("linhas da comanda — tela", () => {
  it("carrega, acrescenta um título e salva no formato do backend", async () => {
    const tela = montar();
    await flushPromises();
    expect(tela.text()).toContain("Água sem gás");

    await tela.find("input[placeholder^='Título']").setValue("Coca-Cola");
    await tela.find("input[placeholder^='Título']").trigger("keydown", { key: "Enter" });
    const botoes = tela.findAll("button");
    await botoes[botoes.length - 1].trigger("click");
    await flushPromises();

    const salvo = chamadas.find((c) => c[0] === "patch");
    expect(salvo[1]).toBe("/restaurants/r1/");
    expect(salvo[2].linhas_da_comanda).toEqual([
      { tipo: "produto", produto: "p1" },
      { tipo: "texto", nome: "Coca-Cola" },
      { tipo: "branco" },
    ]);
  });
});
