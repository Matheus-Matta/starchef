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

describe("recursos de estoque por lote", () => {
  const byName = (name) => resources.find((resource) => resource.name === name);

  it("expoe entradas, saidas, lotes e modelos de etiqueta na Logistica", () => {
    for (const name of ["estoque-entradas", "estoque-saidas", "estoque-lotes", "etiquetas-estoque"]) {
      expect(byName(name), name).toBeDefined();
      expect(byName(name).module, name).toBe("logistica");
    }
  });

  it("expoe o cadastro de fornecedores na Logistica", () => {
    const suppliers = byName("fornecedores");
    expect(suppliers).toBeDefined();
    expect(suppliers.module).toBe("logistica");
    expect(suppliers.endpoint).toBe("/stock/suppliers/");
    expect(suppliers.formFields.map((field) => field.name)).toEqual(
      expect.arrayContaining(["name", "legal_name", "tax_id", "contact_name", "phone", "email"]),
    );
  });

  it("entrada e saida usam tela de documento, nao o formulario generico", () => {
    // Um documento tem uma LISTA de linhas que cresce enquanto o operador
    // digita; o formulario de campos fixos nao representa isso.
    for (const name of ["estoque-entradas", "estoque-saidas"]) {
      const resource = byName(name);
      expect(resource.documentView, name).toBe(true);
      expect(resource.formFields, name).toBeUndefined();
      expect(resource.pro.primaryAction.route, name).toBeTruthy();
      expect(resource.pro.detailRoute, name).toBeTruthy();
    }
  });

  it("entrada e saida oferecem copiar a ultima e duplicar uma existente", () => {
    // Repetir o mesmo documento e a rotina do deposito: a copia abre a tela
    // nova ja preenchida, em vez de obrigar a redigitar linha por linha.
    for (const [name, route] of [
      ["estoque-entradas", "estoque-entrada-nova"],
      ["estoque-saidas", "estoque-saida-nova"],
    ]) {
      const { pro } = byName(name);
      const copyLast = pro.headerActions.find((action) => action.query?.copy === "last");
      expect(copyLast?.routeName, name).toBe(route);
      const duplicate = pro.rowActions.find((action) => action.type === "duplicate");
      expect(duplicate?.routeName, name).toBe(route);
    }
  });

  it("as movimentacoes aceitam o recorte por insumo vindo da posicao de estoque", () => {
    const keys = byName("estoque").pro.linkFilters.map((filter) => filter.key);
    expect(keys).toContain("ingredient");
  });

  it("lotes sao somente leitura: nascem da confirmacao de uma entrada", () => {
    const lots = byName("estoque-lotes");
    expect(lots.endpoint).toBe("/stock/lots/");
    expect(lots.formFields).toBeUndefined();
  });

  it("o modelo de etiqueta traz as medidas do papel adesivo", () => {
    const template = byName("etiquetas-estoque");
    const names = template.formFields.map((field) => field.name);
    expect(names).toEqual(expect.arrayContaining(["width_mm", "height_mm", "margin_mm", "code_type"]));
  });
});

describe("vinculo de consumo de insumo (Fase 0 do plano de estoque)", () => {
  const byName = (name) => resources.find((resource) => resource.name === name);

  it("o adicional declara qual insumo consome e quanto", () => {
    // Sem isto, "bacon extra" vendia sem tirar bacon nenhum do estoque.
    const addon = byName("adicionais");
    const names = addon.formFields.map((field) => field.name);
    expect(names).toEqual(
      expect.arrayContaining(["ingredient", "consumption_quantity", "consumption_unit"]),
    );
    // Campos do Modulo Logistica: nao aparecem para quem nao tem o modulo.
    for (const name of ["ingredient", "consumption_quantity", "consumption_unit"]) {
      expect(addon.formFields.find((field) => field.name === name).module).toBe("logistica");
    }
  });

  it("o produto vendido direto declara o insumo que baixa", () => {
    // O recurso de produtos se chama "cardapio" no config.
    const product = byName("cardapio");
    const names = product.formFields.map((field) => field.name);
    expect(names).toEqual(
      expect.arrayContaining([
        "stock_ingredient",
        "stock_consumption_quantity",
        "stock_consumption_unit",
      ]),
    );
  });
});

describe("cadastro e compra de insumos", () => {
  const byName = (name) => resources.find((resource) => resource.name === name);

  it("vincula o fornecedor padrao ao insumo", () => {
    const ingredient = byName("ingredientes");
    const supplier = ingredient.formFields.find((field) => field.name === "supplier");
    expect(supplier.endpoint).toBe("/stock/suppliers/");
    expect(supplier.module).toBe("logistica");
    expect(ingredient.columns.some((column) => column.key === "supplier_name")).toBe(true);
  });

  it("oferece o formulario repetivel de cadastro em lote", () => {
    const action = byName("ingredientes").pro.headerActions.find((item) => item.key === "bulk-create");
    expect(action.type).toBe("route");
    expect(action.routeName).toBe("ingredientes-lote");
  });
});
