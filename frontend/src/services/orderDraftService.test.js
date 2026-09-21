import { beforeEach, describe, expect, it, vi } from "vitest";

import { materializeDraft } from "./orderDraftService";
import { api } from "./api";

vi.mock("./api", () => ({ api: { post: vi.fn() } }));

const ITEM = (produto) => ({
  product: produto,
  quantity: 1,
  variations: [],
  addons: [],
  customer_note: "",
});

describe("materializeDraft", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.post.mockResolvedValue({ data: { id: "order-1" } });
  });

  it("balcão nasce COM o primeiro item, numa transação só", async () => {
    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      items: [ITEM("p1")],
    });

    expect(api.post).toHaveBeenCalledWith(
      "/orders/create-with-item/",
      expect.objectContaining({ order_type: "counter", restaurant: "rest-1" }),
    );
  });

  it("os itens seguintes entram um a um, depois do pedido existir", async () => {
    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      items: [ITEM("p1"), ITEM("p2"), ITEM("p3")],
    });

    // 1 criação + 2 acréscimos: o primeiro item já foi junto com o pedido.
    expect(api.post).toHaveBeenCalledTimes(3);
    expect(api.post).toHaveBeenCalledWith(
      "/orders/order-1/items/",
      expect.objectContaining({ product: "p2" }),
    );
  });

  it("as comandas são PUXADAS para o pedido, não o contrário", async () => {
    // A comanda não abre pedido — ela anota. O pedido nasce aqui e recebe as
    // anotações pendentes dos cartões.
    await materializeDraft({
      orderType: "command",
      restaurantId: "rest-1",
      commandIds: ["cmd-1"],
      items: [ITEM("p1")],
    });

    expect(api.post).toHaveBeenCalledWith("/orders/order-1/attach-commands/", {
      commands: ["cmd-1"],
    });
  });

  it("varias comandas entram numa conta so", async () => {
    // A mesa que paga junto é o caso, não a exceção — e é UMA chamada, não
    // uma por cartão: duzentas idas ao servidor com o cliente esperando.
    await materializeDraft({
      orderType: "command",
      restaurantId: "rest-1",
      commandIds: ["cmd-1", "cmd-2", "cmd-3"],
      items: [ITEM("p1")],
    });

    const anexos = api.post.mock.calls.filter(([rota]) =>
      rota.endsWith("/attach-commands/"),
    );
    expect(anexos).toHaveLength(1);
    expect(anexos[0][1]).toEqual({ commands: ["cmd-1", "cmd-2", "cmd-3"] });
  });

  it("o pedido nasce com o primeiro item mesmo havendo comanda", async () => {
    // `create-with-item` é atômico: uma falha no meio não deixa pedido vazio.
    await materializeDraft({
      orderType: "command",
      restaurantId: "rest-1",
      commandIds: ["cmd-1"],
      items: [ITEM("p1"), ITEM("p2")],
    });

    expect(api.post.mock.calls[0][0]).toBe("/orders/create-with-item/");
    const acrescimos = api.post.mock.calls.filter(([rota]) =>
      rota.endsWith("/items/"),
    );
    expect(acrescimos).toHaveLength(1);
  });

  it("sem comanda o pedido nao chama o anexo", async () => {
    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      items: [ITEM("p1")],
    });

    const anexos = api.post.mock.calls.filter(([rota]) =>
      rota.endsWith("/attach-commands/"),
    );
    expect(anexos).toHaveLength(0);
  });

  it("rascunho vazio não abre pedido nenhum", async () => {
    await expect(
      materializeDraft({ orderType: "counter", restaurantId: "rest-1", items: [] }),
    ).rejects.toThrow();

    expect(api.post).not.toHaveBeenCalled();
  });

  it("o peso da balança viaja com o item", async () => {
    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      items: [{ ...ITEM("p1"), weight_kg: "0.480", scale_reading: "leitura-1" }],
    });

    expect(api.post).toHaveBeenCalledWith(
      "/orders/create-with-item/",
      expect.objectContaining({
        item: expect.objectContaining({ weight_kg: "0.480", scale_reading: "leitura-1" }),
      }),
    );
  });
});
