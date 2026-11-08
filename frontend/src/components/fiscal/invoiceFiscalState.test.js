import { describe, expect, it } from "vitest";

import { fiscalStateOf, RECREATABLE_STATES } from "./invoiceFiscalState";

describe("situação fiscal da nota na tela", () => {
  it("deriva da nota inteira o mesmo estado que o backend devolve", () => {
    expect(fiscalStateOf({ status: "issued" })).toBe("authorized");
    expect(fiscalStateOf({ status: "error", fiscal_payload: { failure: "configuration" } })).toBe("configuration_error");
    expect(fiscalStateOf({ status: "pending", emission_type: "9", fiscal_payload: { awaiting: "transmission" } }))
      .toBe("contingency_pending");
    expect(fiscalStateOf({ status: "pending", fiscal_payload: { awaiting: "reconciliation" } }))
      .toBe("reconciliation_required");
  });

  it("usa o estado que o resumo do pedido já traz", () => {
    expect(fiscalStateOf({ status: "pending", fiscal_state: "processing" })).toBe("processing");
  });

  it("não oferece recriar o que a SEFAZ pode já ter autorizado", () => {
    // Recriar uma nota em processamento ou em conciliação daria duas notas para a mesma venda.
    expect(RECREATABLE_STATES).not.toContain("processing");
    expect(RECREATABLE_STATES).not.toContain("reconciliation_required");
    expect(RECREATABLE_STATES).not.toContain("authorized");
  });
});
