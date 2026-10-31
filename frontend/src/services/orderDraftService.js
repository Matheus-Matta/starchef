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
 * Criar antes disso enche o banco de pedidos vazios — e a COMANDA nunca cria:
 * ela é um bloco de notas, e o pedido do caixa é que puxa o que ela anotou.
 */

/**
 * Cria o pedido, põe os itens do rascunho dentro e PUXA as comandas escolhidas.
 *
 * A comanda não abre pedido — ela anota. O pedido nasce aqui, no caixa, e
 * recebe as anotações PENDENTES dos cartões que vão ser pagos juntos. São
 * vários de propósito: a mesa grande que paga junto é o caso, não a exceção.
 *
 * Devolve o pedido do servidor. Lança a exceção da API para quem chamou
 * decidir — o rascunho continua intacto na tela, então o operador não perde o
 * que digitou quando a rede falha.
 */
export async function materializeDraft({
  orderType,
  restaurantId,
  commandIds = [],
  customerId = null,
  items = [],
}) {
  // Sem item E sem comanda não há o que abrir. Com um dos dois, há.
  //
  // Exigir um item mesmo cobrando só comandas quebrava o caso CENTRAL do
  // modelo novo: a mesa com dois cartões que chega no caixa para pagar. O
  // operador não tem nada para passar — o consumo já está anotado nos
  // cartões —, e a conta simplesmente não abria.
  if (!items.length && !commandIds.length) {
    throw new Error("Não há itens nem comandas para abrir o pedido.");
  }

  // A mesma porta usada pelo PDV envia pedido, itens e comandas numa transação.
  // Se a rede cair, os UUIDs tornam o reenvio inofensivo.
  const { data } = await api.post("/orders/submit/", {
    id: crypto.randomUUID(),
    order_type: commandIds.length ? "command" : orderType,
    restaurant: restaurantId,
    ...(customerId ? { customer: customerId } : {}),
    items: items.map((item) => ({ id: item.id || crypto.randomUUID(), ..._corpoDoItem(item) })),
    commands: commandIds,
    payments: [],
  });
  return data.order;
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
