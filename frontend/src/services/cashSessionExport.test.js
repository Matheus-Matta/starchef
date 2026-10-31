import { afterEach, describe, expect, it, vi } from "vitest";

import { printCashSessionStatement } from "./cashSessionExport";

describe("cashSessionExport", () => {
  afterEach(() => vi.restoreAllMocks());

  it("imprime os valores do backend traduzidos para português", () => {
    const popup = {
      opener: {},
      document: { write: vi.fn(), close: vi.fn() },
      focus: vi.fn(),
      print: vi.fn(),
    };
    vi.spyOn(window, "open").mockReturnValue(popup);

    const printed = printCashSessionStatement({
      session: {
        cash_station_name: "Caixa 1",
        movements: [{ movement_type: "withdrawal", status: "pending" }],
        sales: [{ order_sequence: 12, card_subtype: "credit" }],
      },
      orders: [{
        sequence: 12,
        order_type: "delivery",
        status: "cancelled",
        payment_status: "cancelled",
        items: [{ status: "comped", addons: [] }],
      }],
    });

    expect(printed).toBe(true);
    const html = popup.document.write.mock.calls[0][0];
    expect(html).toContain("Sangria");
    expect(html).toContain("Pendente");
    expect(html).toContain("Crédito");
    expect(html).toContain("Entrega");
    expect(html).toContain("Cancelado");
    expect(html).toContain("Cortesia");
    expect(html).not.toContain(">withdrawal<");
    expect(html).not.toContain(">credit<");
  });
});
