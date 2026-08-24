import { describe, expect, it } from "vitest";

import { resources } from "./resources";

describe("configuração do cadastro de usuários", () => {
  it("usa a conta da sessão sem exibir ou enviar um seletor de conta", () => {
    const users = resources.find((resource) => resource.name === "usuarios");

    expect(users).toBeDefined();
    expect(users.formFields.some((field) => field.name === "account_scope")).toBe(false);
    expect(users.formFields.some((field) => field.header === "X-Account-ID")).toBe(false);
  });
});
