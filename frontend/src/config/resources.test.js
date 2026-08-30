import { describe, expect, it } from "vitest";

import { resources } from "./resources";

describe("configuração do cadastro de restaurantes", () => {
  it("orienta a cadastrar a senha comum do caixa, sem hash", () => {
    const restaurants = resources.find((resource) => resource.name === "restaurantes");
    const password = restaurants.formFields.find((field) => field.name === "cash_action_password");

    expect(password.type).toBe("password");
    expect(password.configuredField).toBe("has_cash_action_password");
    expect(password.placeholder).toContain("123");
    expect(password.hint).toContain("Não cole uma hash");
  });
});

describe("configuração do cadastro de usuários", () => {
  it("usa a conta da sessão sem exibir ou enviar um seletor de conta", () => {
    const users = resources.find((resource) => resource.name === "usuarios");

    expect(users).toBeDefined();
    expect(users.formFields.some((field) => field.name === "account_scope")).toBe(false);
    expect(users.formFields.some((field) => field.header === "X-Account-ID")).toBe(false);
  });
});

describe("configuração do perfil fiscal", () => {
  const profiles = resources.find((resource) => resource.name === "perfis-fiscais");

  it("é um cadastro da conta, reutilizável por qualquer restaurante", () => {
    expect(profiles).toBeDefined();
    expect(profiles.endpoint).toBe("/fiscal/profiles/");
    expect(profiles.module).toBe("financeiro");
    // Como as categorias: não recebe restaurante/filial automáticos.
    expect(profiles.sharedAcrossRestaurants).toBe(true);
    expect(profiles.formFields.some((field) => field.name === "restaurant")).toBe(false);
    expect(profiles.formFields.some((field) => field.name === "branch")).toBe(false);
  });

  it("traz os campos que a Focus NFe exige para tributar um item", () => {
    const names = profiles.formFields.map((field) => field.name);

    expect(names).toEqual(
      expect.arrayContaining([
        "name", "ncm", "cest", "cfop", "origem", "csosn", "cst_icms",
        "icms_rate", "pis_cst", "pis_rate", "cofins_cst", "cofins_rate", "approx_tax_rate",
      ]),
    );
  });

  it("oferece os códigos oficiais em dropdown, sem digitação livre", () => {
    for (const name of ["origem", "csosn", "cst_icms", "pis_cst", "cofins_cst"]) {
      const field = profiles.formFields.find((item) => item.name === name);
      expect(field.type, name).toBe("dropdown");
      expect(field.options.length, name).toBeGreaterThan(0);
    }
  });
});

describe("ações de notas fiscais", () => {
  const invoices = resources.find((resource) => resource.name === "notas-fiscais");
  const resend = invoices.pro.rowActions.find((action) => action.key === "resend");

  it("oferece reenvio individual apenas para erro ou contingência", () => {
    expect(resend).toMatchObject({ type: "post-detail", action: "resend" });
    expect(resend.visible({ status: "pending", emission_type: "9" })).toBe(true);
    expect(resend.visible({ status: "error", emission_type: "1" })).toBe(true);
    expect(resend.visible({ status: "pending", emission_type: "1" })).toBe(false);
    expect(resend.visible({ status: "issued", emission_type: "1" })).toBe(false);
    expect(invoices.columns.find((column) => column.key === "error_message")).toMatchObject({
      label: "Motivo / erro",
      showInList: false,
    });
  });
});

describe("configuração do produto", () => {
  it("escolhe o perfil fiscal do catálogo compartilhado (relação 1:N)", () => {
    const products = resources.find((resource) => resource.name === "cardapio");
    const fiscal = products.formFields.find((field) => field.name === "fiscal_profile");

    expect(fiscal).toMatchObject({ type: "remote-dropdown", endpoint: "/fiscal/profiles/" });
  });
});

describe("configuração das listagens operacionais", () => {
  it("renderiza os restaurantes do produto como badges", () => {
    const products = resources.find((resource) => resource.name === "cardapio");
    const restaurants = products.columns.find((column) => column.key === "restaurant_names");

    expect(restaurants).toMatchObject({ type: "badges", sortable: false });
  });

  it("identifica o andamento do pedido como status do KDS", () => {
    const orders = resources.find((resource) => resource.name === "pedidos");
    const kds = orders.columns.find((column) => column.key === "production_status");

    expect(kds).toMatchObject({ label: "KDS", type: "kds" });
    expect(kds.map.preparing).toBe("Preparando");
    expect(kds.map.ready).toBe("Pronto");
  });
});
