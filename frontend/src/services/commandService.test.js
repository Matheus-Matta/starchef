import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCommandItems, printCommandReceipt } from "./commandService";
import { api } from "./api";

vi.mock("./api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
}));

/**
 * "O que tem agora" e "o que já teve" são duas perguntas, e a diferença entre
 * elas é um parâmetro só. Errar esse parâmetro faz a comanda reutilizada
 * reaparecer cheia com a conta do cliente anterior — que é o defeito que o
 * campo `command_status` foi criado para evitar.
 */
describe("commandService", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.get.mockResolvedValue({ data: { items: [], closing_merge: null } });
    api.post.mockResolvedValue({ data: {} });
  });

  it("o modo padrao pergunta o que a comanda tem AGORA", async () => {
    await fetchCommandItems("cmd-1");

    expect(api.get).toHaveBeenCalledWith("/commands/cmd-1/items/", { params: {} });
  });

  it("o historico pede explicitamente, e e outro parametro", async () => {
    await fetchCommandItems("cmd-1", { history: true });

    expect(api.get).toHaveBeenCalledWith("/commands/cmd-1/items/", {
      params: { history: 1 },
    });
  });

  it("devolve o closing_merge, que e de onde sai o 'em fechamento'", async () => {
    api.get.mockResolvedValue({ data: { items: [], closing_merge: "merge-9" } });

    const dados = await fetchCommandItems("cmd-1");

    expect(dados.closing_merge).toBe("merge-9");
  });

  it("a conferencia e um POST na comanda, nao no pedido", async () => {
    // Depois do merge o pedido de origem está VAZIO: pedir o recibo por ele
    // produziria um papel em branco.
    await printCommandReceipt("cmd-1");

    expect(api.post).toHaveBeenCalledWith("/commands/cmd-1/receipt/", {});
  });
});
