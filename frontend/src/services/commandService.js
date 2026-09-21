import { api } from "./api";

/**
 * O que uma comanda tem — e o que ela já teve.
 *
 * Estas duas rotas existem porque `command.items` no backend devolve o
 * HISTÓRICO INTEIRO do cartão, inclusive almoços de semanas atrás. Perguntar
 * "o que tem nesta comanda agora" e "o que esta comanda já consumiu" são duas
 * perguntas diferentes, e misturá-las faz a comanda reutilizada reaparecer
 * cheia com a conta de outro cliente.
 *
 * Elas também são o que mantém a comanda legível **depois** da conta agrupada:
 * ali os itens passam a viver no pedido consolidado, e só `OrderItem.command`
 * responde de quem cada um é.
 */

/**
 * Itens da comanda.
 *
 * `history: false` (padrão) devolve só as anotações PENDENTES — o que a
 * comanda deve agora. `history: true` devolve tudo o que o cartão já teve,
 * pendente ou não, que é o que a tela de detalhe mostra.
 */
export async function fetchCommandItems(commandId, { history = false } = {}) {
  const { data } = await api.get(`/commands/${commandId}/items/`, {
    params: history ? { history: 1 } : {},
  });
  return data;
}

/**
 * Imprime a conferência da comanda — funciona antes e depois do merge.
 *
 * **Não é documento fiscal.** A NFC-e é uma só, do pedido consolidado; o papel
 * daqui é o que o cliente pede quando quer saber "e a comanda 13, quanto deu?"
 * dentro de uma conta de quatro pessoas.
 */
export async function printCommandReceipt(commandId) {
  const { data } = await api.post(`/commands/${commandId}/receipt/`, {});
  return data;
}

/** Resolve um cartão lido pelo leitor de código de barras. */
export async function findCommandByCode(code) {
  const { data } = await api.get("/commands/by-code/", { params: { code } });
  return data;
}
