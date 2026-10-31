import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({ api: { get: vi.fn(async () => ({ data: {} })) } }));

import { api } from "./api";
import { LINHAS_DO_RELATORIO, REPORT_CACHE_TTL_MS, endpoints, reportService } from "./reportService";

// A tabela do relatório ordena e pagina no NAVEGADOR. Pedindo 10 linhas, a
// seção de pagamentos mostrava 10 e a tabela achava que eram todas: ordenar
// "do maior para o menor" escolhia o maior entre as 10, não o maior de todos.
describe("reportService", () => {
  beforeEach(() => api.get.mockClear());

  it.each(["sales", "orders", "payment", "waiter", "restaurant", "product", "cash", "command"])(
    "a seção %s pede a lista inteira",
    async (secao) => {
      await reportService.get(secao, { date_from: "2026-10-01" });

      const { params } = api.get.mock.calls[0][1];
      expect(params.page_size).toBe(LINHAS_DO_RELATORIO);
      expect(LINHAS_DO_RELATORIO).toBeGreaterThanOrEqual(1000);
      expect(params.date_from).toBe("2026-10-01");
      expect(api.get.mock.calls[0][1].cacheTtlMs).toBe(REPORT_CACHE_TTL_MS);
    },
  );

  it("o relatório de comandas tem rota própria", async () => {
    await reportService.get("command");

    expect(endpoints.command).toBe("/reports/commands/");
    expect(api.get.mock.calls[0][0]).toBe("/reports/commands/");
  });

  it("permite que atualização manual ignore o cache curto", async () => {
    await reportService.get("sales", {}, { forceRefresh: true });

    expect(api.get.mock.calls[0][1].forceRefresh).toBe(true);
  });
});
