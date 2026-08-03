import { describe, expect, it } from "vitest";
import { normalizeApiError } from "./apiError";

function axiosError({ status, data }) {
  return { response: { status, data } };
}

describe("normalizeApiError", () => {
  it("marca erro de rede quando não há response", () => {
    const result = normalizeApiError({ message: "Network Error" });
    expect(result.isNetwork).toBe(true);
    expect(result.status).toBeNull();
    expect(result.code).toBe("network_error");
  });

  it("separa erros de campo (400) da mensagem geral", () => {
    const err = axiosError({
      status: 400,
      data: { error: { message: { name: ["Este campo é obrigatório."], price: "Valor inválido." } } },
    });
    const result = normalizeApiError(err);
    expect(result.isValidation).toBe(true);
    expect(result.fieldErrors.name).toBe("Este campo é obrigatório.");
    expect(result.fieldErrors.price).toBe("Valor inválido.");
  });

  it("usa a mensagem padrão para 401", () => {
    const err = axiosError({ status: 401, data: {} });
    const result = normalizeApiError(err);
    expect(result.code).toBe("not_authenticated");
    expect(result.message).toMatch(/sessão expirou/i);
  });

  it("usa a mensagem padrão para 403", () => {
    const err = axiosError({ status: 403, data: {} });
    expect(normalizeApiError(err).code).toBe("permission_denied");
  });

  it("mapeia 409 como conflito", () => {
    const err = axiosError({ status: 409, data: {} });
    expect(normalizeApiError(err).code).toBe("conflict");
  });

  it("usa a mensagem padrão para 500", () => {
    const err = axiosError({ status: 500, data: {} });
    const result = normalizeApiError(err);
    expect(result.code).toBe("server_error");
    expect(result.isValidation).toBe(false);
  });

  it("prioriza a mensagem do envelope quando presente (non_field_errors)", () => {
    const err = axiosError({
      status: 400,
      data: { error: { message: { non_field_errors: "Já existe um registro com esse nome." } } },
    });
    expect(normalizeApiError(err).message).toBe("Já existe um registro com esse nome.");
  });
});
