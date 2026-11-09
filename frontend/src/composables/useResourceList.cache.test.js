import { beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "../services/queryClient";
import { useResourceList } from "./useResourceList";

// Voltar de um registro para a lista baixava a lista de novo e a tela esperava
// a rede para mostrar o que tinha mostrado segundos antes.
function servico(resposta, endpoint = "/invoices/") {
  return { endpoint, list: vi.fn(async () => resposta) };
}

describe("useResourceList — cache", () => {
  beforeEach(() => queryClient.clear());

  it("voltar para a mesma lista mostra na hora e não pergunta de novo ao servidor", async () => {
    const service = servico({ results: [{ id: 1 }], count: 1 });
    await useResourceList({ service }).load();

    const volta = useResourceList({ service });
    const carregando = volta.load();

    expect(volta.rows.value).toEqual([{ id: 1 }]);  // antes de qualquer espera
    expect(volta.loading.value).toBe(false);  // sem esqueleto: já tem o que mostrar
    await carregando;
    expect(service.list).toHaveBeenCalledTimes(1);
  });

  it("cache velho aparece na hora e é conferido por baixo", async () => {
    const service = servico({ results: [{ id: 1 }], count: 1 });
    await useResourceList({ service }).load();
    await queryClient.invalidateQueries({ queryKey: ["list", "/invoices/"], refetchType: "none" });
    service.list.mockResolvedValueOnce({ results: [{ id: 2 }], count: 1 });

    const volta = useResourceList({ service });
    const carregando = volta.load();
    expect(volta.rows.value).toEqual([{ id: 1 }]);
    await carregando;

    expect(volta.rows.value).toEqual([{ id: 2 }]);
    expect(service.list).toHaveBeenCalledTimes(2);
  });

  it("outra página ou outro filtro é outra chave", async () => {
    const service = servico({ results: [], count: 90 });
    const lista = useResourceList({ service });
    await lista.load();
    await lista.goToPage(2);

    expect(service.list).toHaveBeenCalledTimes(2);
  });
});
