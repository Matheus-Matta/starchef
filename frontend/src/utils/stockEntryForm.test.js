import { describe, expect, it } from "vitest";

import {
  parseApiDate,
  stockEntryApiErrors,
  toApiDate,
  validateStockEntry,
} from "./stockEntryForm";

const validForm = {
  restaurant: "rest-1",
  location: "loc-1",
  effective_date: new Date(2026, 8, 1),
};

const validRow = {
  _key: 7,
  ingredient: "ing-1",
  package_quantity: 10,
  content_per_package: 1,
  content_unit: "kg",
  manufactured_at: null,
  expires_at: new Date(2026, 11, 1),
  label_count: 1,
};

describe("datas da entrada de estoque", () => {
  it("converte a data da API sem deslocamento de fuso", () => {
    const date = parseApiDate("2026-09-01");
    expect(date.getFullYear()).toBe(2026);
    expect(date.getMonth()).toBe(8);
    expect(date.getDate()).toBe(1);
    expect(toApiDate(date)).toBe("2026-09-01");
  });
});

describe("validateStockEntry", () => {
  it("aponta a linha e o conteúdo por embalagem ausente", () => {
    const result = validateStockEntry({
      form: validForm,
      rows: [{ ...validRow, content_per_package: null }],
    });

    expect(result.valid).toBe(false);
    expect(result.rowErrors["7"].content_per_package).toMatch(/quanto há em cada embalagem/i);
    expect(result.message).toMatch(/Linha 1/i);
  });

  it("exige restaurante e armazém nos campos corretos", () => {
    const result = validateStockEntry({
      form: { ...validForm, restaurant: null, location: null },
      rows: [validRow],
    });

    expect(result.formErrors.restaurant).toMatch(/restaurante/i);
    expect(result.formErrors.location).toMatch(/armazém/i);
  });

  it("exige validade somente ao confirmar quando a filial controla validade", () => {
    const draft = validateStockEntry({ form: validForm, rows: [{ ...validRow, expires_at: null }], expiryRequired: true });
    const posting = validateStockEntry({
      form: validForm,
      rows: [{ ...validRow, expires_at: null }],
      expiryRequired: true,
      forPosting: true,
    });

    expect(draft.valid).toBe(true);
    expect(posting.rowErrors["7"].expires_at).toMatch(/validade/i);
  });
});

describe("stockEntryApiErrors", () => {
  it("preserva o índice e traduz o erro nulo do item", () => {
    const error = {
      response: {
        data: {
          error: {
            message: { items: [{ content_per_package: ["Este campo não pode ser nulo."] }] },
          },
        },
      },
    };

    const result = stockEntryApiErrors(error, [validRow]);

    expect(result.rowErrors["7"].content_per_package).toMatch(/pacote de 1 kg/i);
    expect(result.message).toMatch(/Linha 1/i);
  });
});
