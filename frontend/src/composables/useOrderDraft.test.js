import { beforeEach, describe, expect, it, vi } from "vitest";

import { useOrderDraft } from "./useOrderDraft";
import { materializeDraft } from "../services/orderDraftService";

vi.mock("../services/orderDraftService", () => ({
  materializeDraft: vi.fn(),
}));

const REFRI = { id: "p1", name: "Refrigerante", sale_price: "7.00", pricing_unit: "un" };
const PRATO = { id: "p2", name: "Prato por quilo", sale_price: "59.90", pricing_unit: "kg" };

describe("useOrderDraft", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    materializeDraft.mockResolvedValue({ id: "order-1" });
  });

  it("passar o mesmo produto de novo SOMA, em vez de virar outra linha", () => {
    const rascunho = useOrderDraft();

    rascunho.adicionar(REFRI);
    rascunho.adicionar(REFRI);

    expect(rascunho.itens.value).toHaveLength(1);
    expect(rascunho.itens.value[0].quantity).toBe(2);
  });

  it("observação diferente é outra linha — são dois pedidos do cliente", () => {
    const rascunho = useOrderDraft();

    rascunho.adicionar(REFRI);
    rascunho.adicionar(REFRI, { customer_note: "sem gelo" });

    expect(rascunho.itens.value).toHaveLength(2);
  });

  it("produto por peso NUNCA agrupa: cada pesagem é uma medição", () => {
    const rascunho = useOrderDraft();

    rascunho.adicionar(PRATO, { weight_kg: "0.480", quantity: 0.48 });
    rascunho.adicionar(PRATO, { weight_kg: "0.512", quantity: 0.512 });

    expect(rascunho.itens.value).toHaveLength(2);
  });

  it("anexar comanda NÃO cria pedido nenhum", async () => {
    const rascunho = useOrderDraft();

    rascunho.anexarComanda({ id: "cmd-1", number: 13 });

    expect(materializeDraft).not.toHaveBeenCalled();
    expect(rascunho.tipo.value).toBe("command");
  });

  it("soltar a comanda devolve o rascunho para balcão", () => {
    const rascunho = useOrderDraft();
    rascunho.anexarComanda({ id: "cmd-1", number: 13 });

    rascunho.soltarComanda();

    expect(rascunho.comanda.value).toBeNull();
    expect(rascunho.tipo.value).toBe("counter");
  });

  it("o pedido só nasce ao materializar, e leva a comanda junto", async () => {
    const rascunho = useOrderDraft();
    rascunho.adicionar(REFRI);
    rascunho.anexarComanda({ id: "cmd-1", number: 13 }, { id: "mesa-7" });

    await rascunho.materializar("rest-1");

    expect(materializeDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        orderType: "command",
        commandId: "cmd-1",
        tableId: "mesa-7",
        restaurantId: "rest-1",
      }),
    );
  });

  it("materializar NÃO limpa o rascunho — a navegação seguinte pode falhar", async () => {
    const rascunho = useOrderDraft();
    rascunho.adicionar(REFRI);

    await rascunho.materializar("rest-1");

    expect(rascunho.itens.value).toHaveLength(1);
  });

  it("quantidade zero remove a linha: no rascunho nada foi para a cozinha", () => {
    const rascunho = useOrderDraft();
    const item = rascunho.adicionar(REFRI);

    rascunho.mudarQuantidade(item._id, 0);

    expect(rascunho.itens.value).toHaveLength(0);
  });

  it("o total acompanha preço e quantidade", () => {
    const rascunho = useOrderDraft();

    rascunho.adicionar(REFRI, { quantity: 3 });

    expect(rascunho.total.value).toBeCloseTo(21, 2);
    expect(rascunho.quantidadeDeItens.value).toBe(3);
  });
});
