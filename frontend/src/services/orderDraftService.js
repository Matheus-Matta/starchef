import { api } from "./api";

/**
 * Materializar um rascunho: a hora em que o pedido precisa passar a EXISTIR.
 *
 * Até aqui o carrinho vive só na memória da tela — como num PDV de mercado,
 * onde passar produtos não abre nada em lugar nenhum. O pedido nasce quando
 * alguém de fora precisa dele:
 *
 * * a **cozinha**, que vai imprimir um ticket e produzir;
 * * o **caixa**, que vai anexar um recebimento.
 *
 * Criar antes disso enche o banco de pedidos vazios e prende comandas que
 * ninguém está usando — é o defeito que `order_is_empty` existe para varrer, e
 * ele some quando o pedido não nasce cedo demais.
 */

/**
 * Cria (ou retoma) o pedido e põe todos os itens do rascunho dentro dele.
 *
 * Devolve o pedido do servidor. Lança a exceção da API para quem chamou
 * decidir — o rascunho continua intacto na tela, então o operador não perde o
 * que digitou quando a rede falha.
 */
export async function materializeDraft({
  orderType,
  restaurantId,
  commandId = null,
  tableId = null,
  customerId = null,
  items = [],
}) {
  if (!items.length) throw new Error("Não há itens para abrir o pedido.");

  const pedido = commandId
    ? await _abrirPelaComanda({ commandId, tableId })
    : await _criarComPrimeiroItem({ orderType, restaurantId, customerId, items });

  // Na comanda, TODOS os itens são acrescentados; no balcão, o primeiro já
  // entrou junto com o pedido.
  const restantes = commandId ? items : items.slice(1);
  for (const item of restantes) {
    await api.post(`/orders/${pedido.id}/items/`, _corpoDoItem(item));
  }
  return pedido;
}

/**
 * Comanda: `open-command` cria se o cartão está livre e RETOMA se já há pedido
 * aberto nele.
 *
 * `create-with-item` não serve aqui: ele recusaria com "a comanda já está em
 * uso" no caso normal de o garçom já ter lançado algo nela pelo aplicativo.
 */
async function _abrirPelaComanda({ commandId, tableId }) {
  if (tableId) {
    await api.post(`/commands/${commandId}/link-table/`, { table_id: tableId });
  }
  const { data } = await api.post("/orders/open-command/", { command: commandId });
  return data;
}

/**
 * Balcão, entrega e retirada: o pedido nasce COM o primeiro item.
 *
 * `create-with-item` é atômico — pedido e item na mesma transação. É o que
 * garante que uma falha no meio não deixe um pedido vazio para trás.
 */
async function _criarComPrimeiroItem({ orderType, restaurantId, customerId, items }) {
  const { data } = await api.post("/orders/create-with-item/", {
    order_type: orderType,
    restaurant: restaurantId,
    ...(customerId ? { customer: customerId } : {}),
    item: _corpoDoItem(items[0]),
  });
  return data;
}

function _corpoDoItem(item) {
  return {
    product: item.product,
    quantity: item.quantity,
    variations: item.variations || [],
    addons: item.addons || [],
    customer_note: item.customer_note || "",
    ...(item.weight_kg ? { weight_kg: item.weight_kg } : {}),
    ...(item.scale_reading ? { scale_reading: item.scale_reading } : {}),
  };
}
