import { describe, expect, it } from "vitest";

import { resources } from "./resources";

const invoices = resources.find((resource) => resource.name === "notas-fiscais");

describe("lista de notas fiscais", () => {
  it("ordena das mais recentes e oferece filtros de status e emissao", () => {
    expect(invoices.pro.defaultOrdering).toBe("-created_at");
    expect(invoices.pro.filterFields.map((field) => field.name)).toEqual(["status", "emission_type"]);
    expect(invoices.pro.filterFields.every((field) => field.options.length > 1)).toBe(true);
    expect(invoices.pro.filterFields.every((field) => field.compact)).toBe(true);
  });

  it("mostra o pedido no detalhe e oferece reenvio em massa", () => {
    expect(invoices.columns.find((column) => column.key === "order_sequence")).toMatchObject({
      type: "order-link",
      idKey: "order",
      showInList: false,
    });
    expect(invoices.pro.bulkActions).toContainEqual(expect.objectContaining({
      key: "resend-invoices",
      type: "invoice-bulk-resend",
    }));
  });
});

describe("recriar e baixar o XML", () => {
  const acao = (key) => invoices.pro.rowActions.find((action) => action.key === key);

  it("oferece recriar só para a nota travada, como o reenvio", () => {
    expect(acao("recreate")).toMatchObject({ type: "post-detail", action: "recreate" });
    expect(acao("recreate").visible({ status: "pending", emission_type: "9" })).toBe(true);
    expect(acao("recreate").visible({ status: "error", emission_type: "1" })).toBe(true);
    expect(acao("recreate").visible({ status: "issued", emission_type: "1" })).toBe(false);
    expect(invoices.pro.bulkActions).toContainEqual(expect.objectContaining({
      type: "invoice-bulk-recreate",
      endpoint: "/invoices/bulk-recreate/",
    }));
  });

  it("baixa o XML direto da API só quando a nota tem XML", () => {
    const xml = acao("xml");
    expect(xml.type).toBe("external");
    expect(xml.href({ id: "n1" })).toMatch(/\/invoices\/n1\/xml\/$/);
    expect(xml.visible({ xml_content: "<nfeProc/>" })).toBe(true);
    expect(xml.visible({ xml_content: "" })).toBe(false);
  });

  it("leva à página de exportação em ZIP pelo cabeçalho da lista", () => {
    expect(invoices.pro.headerActions).toContainEqual(expect.objectContaining({
      type: "route",
      routeName: "notas-fiscais-exportar-xml",
    }));
  });
});
