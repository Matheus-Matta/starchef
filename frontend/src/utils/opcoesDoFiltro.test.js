import { describe, expect, it } from "vitest";

import { opcoesDoFiltro, tipoDoFiltro } from "./opcoesDoFiltro";

// O modal de filtros mostrava uma caixa de texto para "Categoria": era preciso
// saber e digitar o id. Agora todo campo com valores conhecidos vira lista.
describe("opcoesDoFiltro", () => {
  it("cadastro relacionado vira lista com as opções buscadas, não caixa de texto", () => {
    const campo = { name: "category", type: "remote-dropdown", endpoint: "/menu/categories/" };
    const opcoes = opcoesDoFiltro(campo, { remotas: { category: [{ label: "Bebidas", value: 12 }] } });

    expect(opcoes).toEqual([{ label: "Bebidas", value: "12" }]);  // texto: casa com o ?f_category=12 da URL
    expect(tipoDoFiltro(campo, opcoes)).toBe("lista");
  });

  it("campo de texto com rótulos na coluna da lista vira lista com esses rótulos", () => {
    const campo = { name: "status", type: "text" };
    const opcoes = opcoesDoFiltro(campo, { colunas: [{ key: "status", map: { paid: "Pago", open: "Aberto" } }] });

    expect(opcoes).toEqual([{ label: "Pago", value: "paid" }, { label: "Aberto", value: "open" }]);
    expect(tipoDoFiltro(campo, opcoes)).toBe("lista");
  });

  it("cada tipo sem valores fixos tem a entrada certa", () => {
    expect(tipoDoFiltro({ type: "boolean" }, [])).toBe("simnao");
    expect(tipoDoFiltro({ type: "money" }, [])).toBe("numero");
    expect(tipoDoFiltro({ type: "date" }, [])).toBe("data");
    expect(tipoDoFiltro({ type: "text" }, [])).toBe("texto");
  });
});
