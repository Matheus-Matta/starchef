import { describe, expect, it } from "vitest";

import { formatReportCell } from "./reportCell";

// Coluna sem tipo mostrava o valor cru do banco: "10.00000000000000".
describe("formatReportCell", () => {
  it("número decimal sem tipo sai com no máximo 2 casas", () => {
    expect(formatReportCell("10.00000000000000", {})).toBe("10");
    expect(formatReportCell("3.14159", {})).toBe("3,14");
    expect(formatReportCell(2.5, {})).toBe("2,5");
  });

  it("quantidade (decimal) também para em 2 casas, salvo se a coluna pedir mais", () => {
    expect(formatReportCell("1.23456", { type: "decimal" })).toBe("1,23");
    expect(formatReportCell("0.375", { type: "decimal", digits: 3 })).toBe("0,375");
  });

  it("dinheiro continua em reais com 2 casas", () => {
    expect(formatReportCell("10.00000000000000", { type: "money" })).toMatch(/R\$\s?10,00/);
  });

  it("texto, código e inteiro não são tocados", () => {
    expect(formatReportCell("0017", {})).toBe("0017");
    expect(formatReportCell("Coca-Cola", {})).toBe("Coca-Cola");
    expect(formatReportCell(42, {})).toBe(42);
    expect(formatReportCell(null, {})).toBe("—");
  });
});
