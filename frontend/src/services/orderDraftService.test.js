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

  it("comanda usa open-command, que CRIA ou RETOMA", async () => {
    // `create-with-item` recusaria com "a comanda já está em uso" no caso
    // normal de o garçom já ter lançado algo nela pelo aplicativo.
    await materializeDraft({
      orderType: "command",
      restaurantId: "rest-1",
      commandId: "cmd-1",
      items: [ITEM("p1")],
    });

    expect(api.post).toHaveBeenCalledWith("/orders/open-command/", { command: "cmd-1" });
  });

  it("na comanda TODOS os itens são acrescentados — nenhum foi junto", async () => {
    await materializeDraft({
      orderType: "command",
      restaurantId: "rest-1",
      commandId: "cmd-1",
      items: [ITEM("p1"), ITEM("p2")],
    });

    const acrescimos = api.post.mock.calls.filter(([rota]) =>
      rota.endsWith("/items/"),
    );
    expect(acrescimos).toHaveLength(2);
  });

  it("comanda com mesa escolhida vincula antes de abrir", async () => {
    await materializeDraft({
      orderType: "command",
      restaurantId: "rest-1",
      commandId: "cmd-1",
      tableId: "mesa-7",
      items: [ITEM("p1")],
    });

    expect(api.post.mock.calls[0]).toEqual([
      "/commands/cmd-1/link-table/",
      { table_id: "mesa-7" },
    ]);
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
