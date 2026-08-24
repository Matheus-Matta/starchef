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
