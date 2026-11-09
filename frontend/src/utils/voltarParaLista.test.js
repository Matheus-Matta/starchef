import { beforeEach, describe, expect, it, vi } from "vitest";

import { esquecerListas, lembrarLista, voltarParaLista } from "./voltarParaLista";

// O "Voltar" do cabeçalho do registro fazia `router.push({ name })`: abria a
// lista pelo endereço limpo e todos os filtros sumiam. Só o Voltar do
// navegador mantinha a lista como estava.
function roteador(anterior) {
  window.history.replaceState({ back: anterior }, "");
  return {
    back: vi.fn(),
    push: vi.fn(),
    resolve: ({ name }) => ({ path: { produtos: "/produtos" }[name] }),
  };
}

describe("voltarParaLista", () => {
  beforeEach(esquecerListas);

  it("veio da lista: volta pelo histórico (filtros, cache e rolagem intactos)", () => {
    const router = roteador("/produtos?pagina=3&f_category=12");

    voltarParaLista(router, "produtos");

    expect(router.back).toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
  });

  it("veio de outro lugar: abre a lista com os últimos filtros usados nela", () => {
    lembrarLista("produtos", { pagina: "3", f_category: "12" });
    const router = roteador("/pedidos");

    voltarParaLista(router, "produtos");

    expect(router.push).toHaveBeenCalledWith({ name: "produtos", query: { pagina: "3", f_category: "12" } });
  });

  it("lista nunca aberta: abre limpa", () => {
    const router = roteador(null);

    voltarParaLista(router, "produtos");

    expect(router.push).toHaveBeenCalledWith({ name: "produtos", query: {} });
  });
});
