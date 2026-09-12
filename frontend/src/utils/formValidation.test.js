import { describe, expect, it } from "vitest";

import { MESSAGES, validateField, validateForm } from "./formValidation";

describe("validateField", () => {
  it("obrigatorio vazio, inclusive multiselect sem item", () => {
    expect(validateField({ name: "name", type: "text", required: true }, "")).toBe(MESSAGES.required);
    expect(validateField({ name: "restaurants", type: "remote-multiselect", required: true }, [])).toBe(MESSAGES.required);
    expect(validateField({ name: "name", type: "text" }, "")).toBe("");
  });

  it("numero inteiro recusa decimal, texto e UUID", () => {
    const field = { name: "display_order", type: "number" };
    expect(validateField(field, "1.5")).toBe(MESSAGES.integer);
    expect(validateField(field, "abc")).toBe(MESSAGES.integer);
    expect(validateField(field, "49040a80-c4eb-4f38-a7a5-9a343770da39")).toBe(MESSAGES.integer);
    expect(validateField(field, "7")).toBe("");
    expect(validateField(field, 0)).toBe("");
  });

  it("nao-negativo por padrao; `min` e `allowNegative` mudam o piso", () => {
    expect(validateField({ name: "sale_price", type: "decimal" }, "-1")).toBe(MESSAGES.negative);
    expect(validateField({ name: "sale_price", type: "decimal" }, "12.90")).toBe("");
    expect(validateField({ name: "number", type: "number", min: 1 }, "0")).toBe(MESSAGES.min(1));
    expect(validateField({ name: "delta", type: "decimal", allowNegative: true }, "-3.5")).toBe("");
    expect(validateField({ name: "x", type: "decimal" }, "1e999")).toBe(MESSAGES.number);
  });

  it("tamanho maximo", () => {
    expect(validateField({ name: "model", type: "text", maxlength: 2 }, "NFE")).toBe(MESSAGES.maxlength(2));
    expect(validateField({ name: "model", type: "text", maxlength: 2 }, "65")).toBe("");
  });

  it("CPF e CNPJ so quando preenchidos", () => {
    const cpf = { name: "document", type: "text", document: "cpf" };
    expect(validateField(cpf, "")).toBe("");
    expect(validateField(cpf, "123.456.789-00")).toBe(MESSAGES.cpf);
    expect(validateField(cpf, "529.982.247-25")).toBe("");
    const cnpj = { name: "cnpj", type: "text", document: "cnpj" };
    expect(validateField(cnpj, "12.345.678/0001")).toBe(MESSAGES.cnpj);
    expect(validateField(cnpj, "12.345.678/0001-95")).toBe("");
  });

  it("regra cruzada: alerta nao passa do tempo-alvo", () => {
    const field = {
      name: "alert_minutes",
      type: "number",
      notGreaterThan: { field: "target_minutes", message: "alerta > alvo" },
    };
    expect(validateField(field, "20", { target_minutes: "15" })).toBe("alerta > alvo");
    expect(validateField(field, "15", { target_minutes: "15" })).toBe("");
    expect(validateField(field, "20", { target_minutes: "" })).toBe("");
  });
});

describe("validateForm", () => {
  it("devolve so os campos com erro", () => {
    const fields = [
      { name: "name", type: "text", required: true },
      { name: "price", type: "decimal" },
      { name: "order", type: "number" },
      { name: "tipo", header: true },
    ];
    expect(validateForm(fields, { name: "Pizza", price: "-1", order: "x" })).toEqual({
      price: MESSAGES.negative,
      order: MESSAGES.integer,
    });
    expect(validateForm(fields, { name: "Pizza", price: "", order: "" })).toEqual({});
  });
});
