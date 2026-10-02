import { describe, expect, it } from "vitest";

import { cnpjDigits, formatCnpj, isValidCnpj } from "./cnpj";

describe("CNPJ", () => {
  it("aceita CNPJ válido com ou sem máscara", () => {
    expect(isValidCnpj("11.222.333/0001-81")).toBe(true);
    expect(isValidCnpj("11222333000181")).toBe(true);
  });

  it("recusa dígito errado, tamanho errado e repetidos", () => {
    expect(isValidCnpj("11.222.333/0001-82")).toBe(false);
    expect(isValidCnpj("1122233300018")).toBe(false);
    expect(isValidCnpj("00000000000000")).toBe(false);
  });

  it("máscara e dígitos", () => {
    expect(formatCnpj("11222333000181")).toBe("11.222.333/0001-81");
    expect(cnpjDigits("11.222.333/0001-81")).toBe("11222333000181");
  });
});
