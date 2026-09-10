import { describe, expect, it } from "vitest";

import { cpfDigits, formatCpf, isValidCpf } from "./cpf";

describe("CPF", () => {
  it("mantém somente os 11 dígitos", () => {
    expect(cpfDigits("123.456.789-09 extra")).toBe("12345678909");
  });

  it("formata enquanto o operador digita", () => {
    expect(formatCpf("12345678909")).toBe("123.456.789-09");
  });

  it("valida os dígitos verificadores", () => {
    expect(isValidCpf("123.456.789-09")).toBe(true);
    expect(isValidCpf("111.111.111-11")).toBe(false);
    expect(isValidCpf("123")).toBe(false);
  });
});
