import { describe, it, expect } from "vitest";
import { formatMoney, roundUpToCent } from "./format";

describe("roundUpToCent", () => {
  it("retorna 0 para valores vazios, zero ou inválidos", () => {
    expect(roundUpToCent(0)).toBe(0);
    expect(roundUpToCent(-5)).toBe(0);
    expect(roundUpToCent(null)).toBe(0);
    expect(roundUpToCent(undefined)).toBe(0);
    expect(roundUpToCent(NaN)).toBe(0);
  });

  it("mantém valores com até 2 casas decimais inalterados (centavos exatos)", () => {
    expect(roundUpToCent(4)).toBe(4);
    expect(roundUpToCent(4.1)).toBe(4.1);
    expect(roundUpToCent(4.16)).toBe(4.16);
    expect(roundUpToCent(10.55)).toBe(10.55);
    expect(roundUpToCent(1.13)).toBe(1.13);
    expect(roundUpToCent(1.14)).toBe(1.14);
    expect(roundUpToCent(29.99)).toBe(29.99);
  });

  it("arredonda 1 centavo para cima quando houver mais de 2 casas decimais", () => {
    // 50 / 12 = 4.166666... -> 4.17
    expect(roundUpToCent(50 / 12)).toBe(4.17);
    // 10 / 3 = 3.333333... -> 3.34
    expect(roundUpToCent(10 / 3)).toBe(3.34);
    // Pequena fração de centavo além de .16
    expect(roundUpToCent(4.1601)).toBe(4.17);
    expect(roundUpToCent(4.161)).toBe(4.17);
    expect(roundUpToCent(4.1667)).toBe(4.17);
    expect(roundUpToCent(4.160001)).toBe(4.17);
    // Menos de 1 centavo vira 1 centavo
    expect(roundUpToCent(0.001)).toBe(0.01);
  });
});

describe("formatMoney", () => {
  it("formata valor em Real", () => {
    const formatted = formatMoney(12.5);
    expect(formatted).toContain("12,50");
  });
});
