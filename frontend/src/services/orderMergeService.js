import { api } from "./api";

// A conferência por comanda vive em `commandService`: ela é operação da
// COMANDA, não da consolidação. Reexportada aqui porque a tela de conta
// agrupada também a oferece, item por item.
export { printCommandReceipt } from "./commandService";

/**
 * A conta agrupada de comandas, do lado do navegador.
 *
 * Uma mesa com quatro comandas de uma família: o pai paga tudo. O caixa lê as
 * quatro (ou inclui à mão), os itens das quatro entram num pedido só, e ele
 * cobra uma vez.
 *
 * Tudo aqui devolve o RESUMO inteiro da consolidação — comandas, itens e
 * total —, e não apenas o registro alterado. É de propósito: a tela precisa
 * redesenhar a lista que o caixa está lendo em voz alta para o cliente, e
 * montá-la de pedaços vindos de respostas diferentes é como ela passa a
 * divergir do servidor.
 */

/** Abre a conta usando o pedido desta comanda como primeira origem. */
export async function openMerge(orderId) {
  const { data } = await api.post(`/orders/${orderId}/merge/`, {});
  return data;
}

export async function fetchMerge(mergeId) {
  const { data } = await api.get(`/orders/merges/${mergeId}/`);
  return data;
}

/**
 * Inclui uma comanda por código escaneado, número impresso ou id.
 *
 * Escanear a mesma comanda de novo é idempotente no servidor: o leitor de
 * código de barras dispara duas leituras com frequência, e transformar isso em
 * erro ensinaria o operador a ignorar mensagens.
 */
export async function addCommand(mergeId, reference) {
  const { data } = await api.post(`/orders/merges/${mergeId}/commands/`, { command: reference });
  return data;
}

export async function removeCommand(mergeId, commandId) {
  const { data } = await api.delete(`/orders/merges/${mergeId}/commands/${commandId}/`);
  return data;
}

/**
 * Confirma: os itens das comandas passam para um pedido só.
 *
 * `Idempotency-Key` é obrigatória aqui porque esta é a operação que move
 * dinheiro entre pedidos. Sem ela, um clique duplo (ou um reenvio da rede)
 * poderia disparar duas consolidações da mesma mesa.
 */
export async function confirmMerge(mergeId, idempotencyKey) {
  const { data } = await api.post(
    `/orders/merges/${mergeId}/confirm/`,
    {},
    { headers: { "Idempotency-Key": idempotencyKey } },
  );
  return data;
}

export async function cancelMerge(mergeId, reason = "") {
  const { data } = await api.post(`/orders/merges/${mergeId}/cancel/`, { reason });
  return data;
}

/**
 * Estorna a conta agrupada JÁ PAGA.
 *
 * Não é o mesmo que `cancelMerge`. Desfazer devolve os itens às comandas de uma
 * conta que ainda não recebeu dinheiro; estornar desmonta uma venda que já
 * passou por caixa, estoque e nota — e esvazia os cartões, **inclusive
 * cancelando o pedido de um cartão que já foi reentregue a outro cliente**.
 *
 * Exige gerente e motivo. A resposta traz o relatório do que foi desfeito.
 */
export async function refundMerge(mergeId, reason) {
  const { data } = await api.post(`/orders/merges/${mergeId}/refund/`, { reason });
  return data;
}

/** As comandas livres/ocupadas do restaurante, para a inclusão à mão. */
export async function searchCommands(term) {
  const { data } = await api.get("/commands/", { params: { search: term, page_size: 20 } });
  return data?.results || data || [];
}
