import { describe, expect, it, vi } from "vitest";

import { useResourceList } from "./useResourceList";

// Clicar no título da coluna ordenava só as 25 linhas da página: o servidor
// ignorava a coluna e a tabela reordenava o que tinha na mão. Agora a ordem é
// do servidor, e a tabela só oferece ordenar a coluna que ele sabe ordenar.
function servico(resposta) {
  return { list: vi.fn(async () => resposta) };
}

describe("useResourceList — ordenação", () => {
  it("ordenar pede ao servidor e volta para a página 1", async () => {
    const service = servico({ results: [], count: 90, orderable: ["customer_name"] });
    const lista = useResourceList({ service });
    await lista.goToPage(3);

    await lista.setSort("customer_name", -1);

    const params = service.list.mock.calls.at(-1)[0];
    expect(params.ordering).toBe("-customer_name");
    expect(params.page).toBe(1);
  });

  it("só oferece ordenar a coluna que o servidor sabe ordenar", async () => {
    const lista = useResourceList({
      service: servico({ results: [], count: 0, orderable: ["customer_name", "status"] }),
    });
    await lista.load();

    expect(lista.canSort("customer_name")).toBe(true);
    expect(lista.canSort("command_label")).toBe(false);
  });

  it("servidor antigo, sem a lista de ordenáveis: nenhuma coluna perde a ordenação", async () => {
    const lista = useResourceList({ service: servico({ results: [], count: 0 }) });
    await lista.load();

    expect(lista.canSort("qualquer_coluna")).toBe(true);
  });

  it("limpar a ordenação (terceiro clique) volta à ordem padrão do servidor", async () => {
    const service = servico({ results: [], count: 0, orderable: ["status"] });
    const lista = useResourceList({ service });
    await lista.setSort("status", 1);

    await lista.setSort("status", 0);

    expect(service.list.mock.calls.at(-1)[0].ordering).toBeUndefined();
  });

  it("erro do servidor não deixa a tabela com colunas presas sem ordenação", async () => {
    const service = { list: vi.fn().mockRejectedValue(new Error("caiu")) };
    const lista = useResourceList({ service });
    await lista.load();

    expect(lista.canSort("status")).toBe(true);
  });
});
