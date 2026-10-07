import { describe, expect, it, vi } from "vitest";

import { enviarImportacao } from "./importUpsert";

// A planilha vai ao servidor numa chamada só: a tela não espera linha a linha.
describe("enviarImportacao", () => {
  it("resolve as relações e manda o lote inteiro de uma vez", async () => {
    const api = { post: vi.fn().mockResolvedValue({ data: { id: "job-1", status: "queued" } }) };
    const servico = { list: vi.fn().mockResolvedValue({ results: [{ id: "f1", name: "Ambev" }], next: null }) };
    const fields = [
      { name: "name", type: "text" },
      { name: "supplier", label: "Fornecedor", type: "remote-dropdown", endpoint: "/stock/suppliers/" },
    ];

    const { job, warnings } = await enviarImportacao({
      api, endpoint: "/menu/ingredients/", fields,
      payloads: [{ name: "Coca", supplier: "ambev" }, { name: "Guaraná", supplier: "Nenhum" }],
      servicoPara: () => servico,
    });

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith("/imports/", {
      endpoint: "/menu/ingredients/", key: "name",
      rows: [{ name: "Coca", supplier: "f1" }, { name: "Guaraná" }],
    });
    expect(job.id).toBe("job-1");
    expect(warnings).toHaveLength(1);
  });
});
