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

  const pedido = items.length
    ? await _criarComPrimeiroItem({
        orderType: commandIds.length ? "command" : orderType,
        restaurantId,
        customerId,
        items,
      })
    : await _criarParaComandas({ restaurantId, customerId });

  // O primeiro item já entrou junto com o pedido; os outros vão em seguida.
  // Sem item nenhum, `slice(1)` é vazio e o laço não roda.
  for (const item of items.slice(1)) {
    await api.post(`/orders/${pedido.id}/items/`, _corpoDoItem(item));
  }

  // E então as comandas: o pedido PUXA as anotações pendentes dos cartões.
  if (commandIds.length) {
    const { data } = await api.post(`/orders/${pedido.id}/attach-commands/`, {
      commands: commandIds,
    });
    return data;
  }
  return pedido;
}

/**
 * Só comandas: o pedido nasce VAZIO e as anotações o preenchem.
 *
 * É o caminho da mesa que chega no caixa sem nada novo para passar.
 * `create-with-item` não serve aqui porque não há item; o pedido vazio dura o
 * tempo de uma chamada, até `attach-commands` puxar o que os cartões anotaram.
 */
async function _criarParaComandas({ restaurantId, customerId }) {
  const { data } = await api.post("/orders/", {
    order_type: "command",
    restaurant: restaurantId,
    ...(customerId ? { customer: customerId } : {}),
  });
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
