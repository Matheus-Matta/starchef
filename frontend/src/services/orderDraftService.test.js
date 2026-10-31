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
    api.post.mockResolvedValue({ data: { order: { id: "order-1" } } });
  });

  it("balcão nasce com todos os itens numa transação só", async () => {
    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      items: [ITEM("p1")],
    });

    expect(api.post).toHaveBeenCalledWith(
      "/orders/submit/",
      expect.objectContaining({
        order_type: "counter",
        restaurant: "rest-1",
        items: [expect.objectContaining({ product: "p1" })],
      }),
    );
  });

  it("os itens seguintes viajam no mesmo pedido ao servidor", async () => {
    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      items: [ITEM("p1"), ITEM("p2"), ITEM("p3")],
    });

    expect(api.post).toHaveBeenCalledTimes(1);
    const [, payload] = api.post.mock.calls[0];
    expect(payload.items.map((item) => item.product)).toEqual(["p1", "p2", "p3"]);
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

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post.mock.calls[0][1].commands).toEqual(["cmd-1"]);
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

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post.mock.calls[0][1].commands).toEqual(["cmd-1", "cmd-2", "cmd-3"]);
  });

  it("o pedido nasce com o primeiro item mesmo havendo comanda", async () => {
    // `/submit/` é atômico: uma falha no meio não deixa pedido vazio.
    await materializeDraft({
      orderType: "command",
      restaurantId: "rest-1",
      commandIds: ["cmd-1"],
      items: [ITEM("p1"), ITEM("p2")],
    });

    expect(api.post.mock.calls[0][0]).toBe("/orders/submit/");
    const acrescimos = api.post.mock.calls.filter(([rota]) =>
      rota.endsWith("/items/"),
    );
    expect(acrescimos).toHaveLength(0);
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

  it("rascunho vazio de tudo não abre pedido nenhum", async () => {
    await expect(
      materializeDraft({ orderType: "counter", restaurantId: "rest-1", items: [] }),
    ).rejects.toThrow();

    expect(api.post).not.toHaveBeenCalled();
  });

  it("SO comandas abre a conta, sem exigir item novo", async () => {
    // O caso central do modelo novo: a mesa com dois cartões chega no caixa e
    // o operador não tem nada para passar — o consumo já está anotado neles.
    // Exigir um item aqui fazia a conta simplesmente não abrir.
    api.post.mockResolvedValue({ data: { order: { id: "order-1" } } });

    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      commandIds: ["c-1", "c-2"],
      items: [],
    });

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post.mock.calls[0][0]).toBe("/orders/submit/");
    expect(api.post.mock.calls[0][1]).toMatchObject({
      order_type: "command",
      restaurant: "rest-1",
      commands: ["c-1", "c-2"],
      items: [],
    });
  });

  it("so comandas também passa pela venda inteira", async () => {
    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      commandIds: ["c-1"],
      items: [],
    });

    expect(api.post.mock.calls.map(([caminho]) => caminho)).toEqual(["/orders/submit/"]);
  });

  it("so comandas com cliente leva o cliente junto", async () => {
    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      commandIds: ["c-1"],
      customerId: "cli-9",
      items: [],
    });

    expect(api.post.mock.calls[0][1]).toMatchObject({ customer: "cli-9" });
  });

  it("o peso da balança viaja com o item", async () => {
    await materializeDraft({
      orderType: "counter",
      restaurantId: "rest-1",
      items: [{ ...ITEM("p1"), weight_kg: "0.480", scale_reading: "leitura-1" }],
    });

    expect(api.post).toHaveBeenCalledWith(
      "/orders/submit/",
      expect.objectContaining({
        items: [expect.objectContaining({ weight_kg: "0.480", scale_reading: "leitura-1" })],
      }),
    );
  });
});
