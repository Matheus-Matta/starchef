import '../../../core/data/order_item_status.dart';

/// O que fazer com o pedido quando o operador SAI dele.
enum OrderExit {
  /// Deixa como está: tem venda de verdade dentro, ou já foi concluído.
  keep,

  /// Descarta: nasceu e não virou nada.
  discard,

  /// Solta os cartões primeiro, depois descarta.
  releaseCommands,
}

/// A decisão de saída de um pedido — sem tela, sem rede, sem `setState`.
///
/// Mora fora da página porque é a regra que mais custou caro. Três estados
/// parecidos, com consequências muito diferentes:
///
/// * **vazio** — nasceu ao abrir a tela e o operador voltou. Cancelar é
///   inofensivo: não há consumo nenhum;
/// * **só cartões** — a conta não tem nada PRÓPRIO; tudo o que ela mostra são
///   cópias das anotações dos cartões. Ela não é vazia, então o descarte não a
///   alcançava: o operador ia ao pagamento, voltava sem concluir, e a conta
///   ficava aberta para sempre segurando o consumo. Na tentativa seguinte o
///   servidor recusava e a comanda parecia travada, com os itens à vista.
///
///   E cancelá-la seria pior: `cancel_order` marca as anotações como PERDA —
///   comida comida, lançada como prejuízo. O caminho é soltar os cartões
///   ([OrderExit.releaseCommands]), que devolve tudo a pendente;
/// * **com venda** — tem item passado no caixa ou recebimento registrado.
///   Isso é venda de alguém; sair da tela não pode mexer nela.
OrderExit decideOrderExit({
  required Map<String, dynamic>? order,
  required List<Map<String, dynamic>> items,
  required bool hasPayments,
}) {
  if (order == null) return OrderExit.keep;
  // Pago, cancelado ou estornado já tem destino. Mexer aqui reescreveria o
  // histórico de uma venda fechada.
  if (const {
    'paid',
    'cancelled',
    'refunded',
  }.contains('${order['status'] ?? ''}')) {
    return OrderExit.keep;
  }
  // Recebimento registrado é dinheiro que entrou: só o cancelamento de
  // verdade, com motivo e autorização, pode desfazer isso.
  if (hasPayments) return OrderExit.keep;

  final contam = items.where(OrderItemStatus.countsTowardBill).toList();
  if (contam.isEmpty) return OrderExit.discard;
  return contam.every(veioDeComanda)
      ? OrderExit.releaseCommands
      : OrderExit.keep;
}

/// O item do pedido é cópia de uma anotação de cartão?
bool veioDeComanda(Map<String, dynamic> item) =>
    '${item['command'] ?? ''}'.trim().isNotEmpty;

/// Os cartões cujas anotações este pedido pegou, sem repetir.
Set<String> commandsHeldBy(List<Map<String, dynamic>> items) => {
  for (final item in items)
    if (veioDeComanda(item)) '${item['command']}'.trim(),
};
