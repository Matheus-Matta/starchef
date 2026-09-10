/// Vocabulário de status de item de pedido — e a única resposta para a
/// pergunta "este item entra na conta?".
///
/// O servidor responde isso num lugar só: `recalculate_order` soma os itens
/// excluindo `cancelled` e `comped`. O PDV respondia em sete lugares
/// diferentes, cada um com um recorte próprio — um esquecia `comped`, outro
/// esquecia `cancelled`, e a soma do total esquecia os dois. Era isso que
/// fazia o PDV fechar com um valor maior que o do servidor: o item que o
/// cliente desistiu continuava somando aqui, e o `expected_total` do
/// fechamento chegava divergente.
///
/// Nada aqui é opinião do PDV: a lista é a mesma do backend. Quando um status
/// novo sair de conta lá, ele entra aqui — e todo mundo passa a respeitar
/// junto.
class OrderItemStatus {
  const OrderItemStatus._();

  /// Cancelado: o item saiu da conta e do faturamento.
  static const String cancelled = 'cancelled';

  /// Cortesia: o item foi entregue mas não é cobrado.
  static const String comped = 'comped';

  /// Status LEGADO, que só existiu dentro deste terminal.
  ///
  /// O cancelamento offline gravava `voided` enquanto o servidor gravava
  /// `cancelled`, então o MESMO item tinha dois nomes dependendo de a operação
  /// já ter sincronizado ou não. A gravação foi unificada em [cancelled], mas
  /// os pedidos que já estão no SQLite das lojas seguem com `voided` — e
  /// continuam tendo de ficar fora da conta.
  static const String legacyVoided = 'voided';

  /// Os status que NÃO entram no subtotal, na nota nem no recibo.
  static const Set<String> outOfBill = {cancelled, comped, legacyVoided};

  static bool isOutOfBill(Map<String, dynamic> item) =>
      outOfBill.contains('${item['status'] ?? ''}');

  /// Predicado para `where`: o item soma no total do pedido.
  static bool countsTowardBill(Map<String, dynamic> item) =>
      !isOutOfBill(item);
}
