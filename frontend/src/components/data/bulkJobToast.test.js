import { describe, expect, it } from "vitest";

import { bulkJobToast } from "./bulkJobToast";

describe("aviso de operação em lote", () => {
  it("avisa para aguardar sem fingir que o trabalho já terminou", () => {
    const toast = bulkJobToast({ total: 20 }, "comandas");

    expect(toast.summary).toBe("Processamento iniciado");
    expect(toast.detail).toContain("Aguarde");
    expect(toast.detail).toContain("sino");
  });
});
