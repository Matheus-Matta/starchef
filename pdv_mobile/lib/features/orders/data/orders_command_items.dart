part of 'orders_repository.dart';

/// A COMANDA COMO BLOCO DE NOTAS — as operações do cartão.
///
/// O garçom anota o consumo e manda para a produção; nenhum pedido é aberto. O
/// pedido só nasce no caixa, com as anotações pendentes.
///
/// Ficam em arquivo próprio porque são um assunto: antes isto era uma linha só
/// (`open-command`), e virou o gesto central do aplicativo.
extension OrdersCommandItems on OrdersRepository {
  /// Anota um consumo NA COMANDA. Nenhum pedido é aberto.
  ///
  /// É o gesto central do garçom no modelo novo: o cartão é um bloco de notas,
  /// e o pedido só nasce no caixa, com as anotações pendentes. Antes isto era
  /// `open-command`, que criava um pedido para o cartão — e era esse gesto que
  /// prendia a comanda a um pedido que talvez ninguém fosse pagar.
  ///
  /// Passa pela MESMA fila de `mutate`: o garçom lança com o celular no bolso
  /// e a rede do salão caindo, e a anotação sobe quando der.
  Future<Map<String, dynamic>> launchCommandItem({
    required String commandId,
    required String productId,
    required String productName,
    required int quantity,
    String customerNote = '',
    List<String> addonIds = const [],
    String? variationId,
  }) => mutate(
    method: 'POST',
    path: '/commands/$commandId/items/',
    kind: 'launch_command_item',
    summary: '${quantity}x $productName',
    body: {
      'product': productId,
      'quantity': quantity,
      'variations': variationId == null ? const [] : [variationId],
      'addons': addonIds,
      'customer_note': customerNote,
    },
  );

  /// Manda a rodada pendente da comanda para a produção.
  Future<Map<String, dynamic>> sendCommandToKitchen(String commandId) => mutate(
    method: 'POST',
    path: '/commands/$commandId/send-to-kitchen/',
    kind: 'send_command_kitchen',
    summary: 'Enviar comanda à cozinha',
    body: const {},
  );

  /// Cancela uma anotação. Ela sai da comanda como PERDA, não como venda.
  Future<Map<String, dynamic>> voidCommandItem({
    required String commandId,
    required String itemId,
    required String itemLabel,
    required String reason,
  }) => mutate(
    method: 'DELETE',
    path: '/commands/$commandId/items/$itemId/void/',
    kind: 'void_command_item',
    summary: 'Cancelar $itemLabel',
    body: {'reason': reason},
  );
}
