import { describe, expect, it } from "vitest";

import { cnpjDigits, formatCnpj, isValidCnpj } from "./cnpj";

// A mesma regra do backend (`customers/validators.py`) e do PDV desktop: o
// CNPJ alfanumérico da Receita tem letras nas 12 primeiras posições.
describe("CNPJ", () => {
  it("aceita o numérico e o alfanumérico, com ou sem máscara", () => {
    expect(isValidCnpj("11.222.333/0001-81")).toBe(true);
    expect(isValidCnpj("11222333000181")).toBe(true);
    expect(isValidCnpj("12.ABC.345/01DE-35")).toBe(true);
    expect(isValidCnpj("12abc34501de35")).toBe(true);
  });

  it("recusa dígito errado, letra no verificador, tamanho errado e repetidos", () => {
    expect(isValidCnpj("11.222.333/0001-82")).toBe(false);
    expect(isValidCnpj("11.222.333/0001-8A")).toBe(false);
    expect(isValidCnpj("1122233300018")).toBe(false);
    expect(isValidCnpj("00000000000000")).toBe(false);
    expect(isValidCnpj("")).toBe(false);
    expect(isValidCnpj(null)).toBe(false);
  });

  it("máscara e caracteres úteis, mantendo as letras em maiúscula", () => {
    expect(formatCnpj("11222333000181")).toBe("11.222.333/0001-81");
    expect(formatCnpj("12abc34501de35999")).toBe("12.ABC.345/01DE-35");
    expect(cnpjDigits("12.abc.345/01de-35")).toBe("12ABC34501DE35");
  });
});
