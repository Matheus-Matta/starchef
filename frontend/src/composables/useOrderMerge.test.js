import { describe, expect, it, vi, beforeEach } from "vitest";

import { useOrderMerge } from "./useOrderMerge";
import * as service from "../services/orderMergeService";

vi.mock("../services/orderMergeService");

const CONTA = {
  id: "merge-1",
  status: "open",
  target_order: "order-destino",
  subtotal: "35.00",
  service_fee: "2.02",
  discount: "0.00",
  total: "37.02",
  sources: [
    { command: "cmd-1", command_number: 13, table_number: "7" },
    { command: "cmd-2", command_number: 14, table_number: "7" },
  ],
  items: [
    { id: "i1", command: "cmd-1", command_number: 13, product_name: "X-Burger", total_price: "25.00", quantity: 1 },
    { id: "i2", command: "cmd-2", command_number: 14, product_name: "Refri", total_price: "10.00", quantity: 1 },
  ],
};

describe("useOrderMerge", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("agrupa os itens por comanda — e a ordem é a do numero impresso", async () => {
    service.fetchMerge.mockResolvedValue({
      ...CONTA,
      items: [...CONTA.items].reverse(),
    });
    const merge = useOrderMerge();
    await merge.load("merge-1");

    const grupos = merge.itemsByCommand.value;
    expect(grupos).toHaveLength(2);
    expect(grupos[0].number).toBe(13);
    expect(grupos[0].total).toBe(25);
    expect(grupos[1].number).toBe(14);
  });

  it("reenvia a MESMA chave de idempotencia em dois cliques em confirmar", async () => {
    service.openMerge.mockResolvedValue(CONTA);
    service.confirmMerge.mockResolvedValue({ ...CONTA, status: "confirmed" });
    const merge = useOrderMerge();
    await merge.start("order-1");

    await merge.confirm();
    await merge.confirm();

    const [, primeira] = service.confirmMerge.mock.calls[0];
    const [, segunda] = service.confirmMerge.mock.calls[1];
    expect(primeira).toBeTruthy();
    expect(segunda).toBe(primeira);
  });

  it("marca conflito quando o servidor responde 409", async () => {
    service.openMerge.mockResolvedValue(CONTA);
    service.addCommand.mockRejectedValue({
      response: { status: 409, data: { detail: "A comanda 13 já está em outra conta agrupada." } },
    });
    const merge = useOrderMerge();
    await merge.start("order-1");

    await merge.include("13");

    expect(merge.conflict.value).toBe(true);
    expect(merge.error.value).toContain("outra conta");
  });

  it("um 400 nao e conflito — e erro de entrada, que tentar de novo resolve", async () => {
    service.openMerge.mockResolvedValue(CONTA);
    service.addCommand.mockRejectedValue({
      response: { status: 400, data: { detail: "Comanda '999' não encontrada neste restaurante." } },
    });
    const merge = useOrderMerge();
    await merge.start("order-1");

    await merge.include("999");

    expect(merge.conflict.value).toBe(false);
  });

  it("ignora leitura vazia em vez de chamar o servidor", async () => {
    service.openMerge.mockResolvedValue(CONTA);
    const merge = useOrderMerge();
    await merge.start("order-1");

    await merge.include("   ");

    expect(service.addCommand).not.toHaveBeenCalled();
  });
});

describe("useOrderMerge — estorno e conferência", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  const PAGA = { ...CONTA, status: "paid" };

  it("estornar devolve o relatorio do que foi desfeito", async () => {
    service.fetchMerge.mockResolvedValue(PAGA);
    service.refundMerge.mockResolvedValue({
      ...PAGA,
      status: "cancelled",
      refund: {
        commands_emptied: ["cmd-1", "cmd-2"],
        reused_orders_discarded: [{ id: "o9", sequence: 41 }],
      },
    });
    const merge = useOrderMerge();
    await merge.load("merge-1");

    const relatorio = await merge.refund("Cobrança em duplicidade");

    expect(service.refundMerge).toHaveBeenCalledWith("merge-1", "Cobrança em duplicidade");
    expect(relatorio.commands_emptied).toHaveLength(2);
    // O pedido do cartão já reentregue aparece no relatório: alguém vai
    // perguntar por ele depois.
    expect(relatorio.reused_orders_discarded[0].sequence).toBe(41);
  });

  it("isPaid distingue a conta paga da confirmada", async () => {
    service.fetchMerge.mockResolvedValue(PAGA);
    const merge = useOrderMerge();
    await merge.load("merge-1");

    expect(merge.isPaid.value).toBe(true);
    expect(merge.isConfirmed.value).toBe(false);
  });

  it("a conferencia de uma comanda nao apaga a conta da tela", async () => {
    service.fetchMerge.mockResolvedValue(CONTA);
    service.printCommandReceipt.mockResolvedValue({ total: "25.00" });
    const merge = useOrderMerge();
    await merge.load("merge-1");

    await merge.receipt("cmd-1");

    expect(service.printCommandReceipt).toHaveBeenCalledWith("cmd-1");
    expect(merge.merge.value).toEqual(CONTA);
  });

  it("falha ao imprimir vira mensagem, nao excecao", async () => {
    service.fetchMerge.mockResolvedValue(CONTA);
    service.printCommandReceipt.mockRejectedValue({
      response: { status: 400, data: { detail: "Nenhuma impressora ativa." } },
    });
    const merge = useOrderMerge();
    await merge.load("merge-1");

    await merge.receipt("cmd-1");

    expect(merge.error.value).toContain("impressora");
  });
});
