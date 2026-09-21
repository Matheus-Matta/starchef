import { describe, expect, it, vi, beforeEach } from "vitest";
import { nextTick, ref } from "vue";

vi.mock("../services/commandService", () => ({
  fetchCommandItems: vi.fn(),
  printCommandReceipt: vi.fn(),
}));

import { fetchCommandItems } from "../services/commandService";
import { useCommandItems } from "./useCommandItems";

/**
 * O cartão aberto mostra o que ele TEM e o que ele JÁ TEVE, de uma vez.
 *
 * Eram duas abas e duas consultas, e quem abria a comanda via só a primeira —
 * mas é conferindo o que já passou que o operador resolve uma reclamação de
 * conta ou descobre que o item foi cancelado e não sumiu.
 */
const ITENS = [
  { id: "1", command_status: "pending", total_price: "10.00" },
  { id: "2", command_status: "pending", total_price: "5.50" },
  { id: "3", command_status: "billed", total_price: "40.00" },
  { id: "4", command_status: "cancelled", total_price: "7.00" },
];

async function montar(itens = ITENS) {
  fetchCommandItems.mockResolvedValue({ items: itens });
  const estado = useCommandItems(ref({ id: "c-7" }));
  await nextTick();
  await nextTick();
  return estado;
}

describe("useCommandItems", () => {
  beforeEach(() => vi.clearAllMocks());

  it("pede o histórico COMPLETO numa consulta só", async () => {
    await montar();

    expect(fetchCommandItems).toHaveBeenCalledTimes(1);
    expect(fetchCommandItems).toHaveBeenCalledWith("c-7", { history: true });
  });

  it("separa o que está aberto do que já passou", async () => {
    const { pendentes, fechados } = await montar();

    expect(pendentes.value.map((i) => i.id)).toEqual(["1", "2"]);
    expect(fechados.value.map((i) => i.id)).toEqual(["3", "4"]);
  });

  it("o total que vira dinheiro é SÓ o que está aberto", async () => {
    // Somar o histórico cobraria de novo o que já foi pago.
    const { total } = await montar();

    expect(total.value).toBe(15.5);
  });

  it("o total do histórico fica à parte, para conferência", async () => {
    const { totalHistorico } = await montar();

    expect(totalHistorico.value).toBe(47);
  });

  it("cartão reutilizado mostra o aberto VAZIO e o passado marcado", async () => {
    // O defeito que a separação existe para impedir: a comanda do cliente
    // anterior reaparecendo cheia para quem acabou de sentar.
    const { pendentes, fechados, total } = await montar([
      { id: "9", command_status: "billed", total_price: "80.00" },
    ]);

    expect(pendentes.value).toEqual([]);
    expect(total.value).toBe(0);
    expect(fechados.value).toHaveLength(1);
  });

  it("falha na leitura não deixa item velho na tela", async () => {
    fetchCommandItems.mockRejectedValue({ response: { data: { detail: "sem rede" } } });
    const estado = useCommandItems(ref({ id: "c-7" }));
    await nextTick();
    await nextTick();

    expect(estado.erro.value).toBe("sem rede");
    expect(estado.itens.value).toEqual([]);
  });
});
