part of 'orders_repository.dart';

/// A RODADA EM SEGUNDO PLANO: os itens e o "enviar à cozinha" vão para a fila
/// e a tela é liberada na hora.
///
/// Antes o garçom ficava parado no carregando enquanto cada item subia, um a
/// um, e só então a rodada ia para a produção — com a rede do salão ruim eram
/// dezenas de segundos com o cliente olhando. Agora tudo entra na fila (em
/// disco, FIFO) e o envio acontece sem ele: o contador do topo da tela inicial
/// mostra o que ainda está a caminho, e o que não sair em 4 tentativas aparece
/// em "não enviados" com o botão de reenviar.
extension OrdersRodada on OrdersRepository {
  /// Enfileira a rodada inteira. Volta assim que estiver salva no aparelho.
  Future<void> enfileirarRodada({
    required OrderSubject subject,
    required List<DraftItem> itens,
    Map<String, String>? metafields,
  }) async {
    final base = subject.isCommand ? '/commands' : '/orders';
    for (final item in itens) {
      await gateway.enqueue(
        method: 'POST',
        path: '$base/${subject.id}/items/',
        // O mesmo `kind` do envio direto: é por ele que a tela de detalhe
        // mostra o item como "a caminho".
        kind: 'add_item',
        summary: item.label,
        body: {
          // Identidade da anotação: é ela que deixa o envio cair na nuvem com
          // segurança quando a loja não responde (`cloud_fallback.dart`) — se
          // as duas pontas gravarem, a sincronização junta numa linha só.
          if (subject.isCommand) 'id': OperationId.uuid(),
          'product': item.productId,
          'quantity': item.quantity,
          'variations': item.variationId == null
              ? const []
              : [item.variationId],
          'addons': item.addonIds,
          'customer_note': item.note,
          'metafields': ?metafields,
        },
      );
    }
    await gateway.enqueue(
      method: 'POST',
      path: '$base/${subject.id}/send-to-kitchen/',
      kind: 'send_to_kitchen',
      summary: subject.isCommand
          ? 'Enviar comanda à cozinha'
          : 'Enviar pedido para a cozinha',
      body: const {},
    );
  }
}
