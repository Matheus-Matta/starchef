part of 'orders_repository.dart';

/// As mesmas quatro operações, no endereço certo para pedido ou comanda.
///
/// Fica aqui, e não espalhado em `if (isCommand)` dentro do apresentador,
/// porque a diferença entre os dois é de ENDEREÇO — e endereço é assunto do
/// repositório. O apresentador passou a não saber qual dos dois está aberto,
/// exceto onde a regra de verdade muda (cobrar).
extension OrdersSubjectApi on OrdersRepository {
  /// O atendimento inteiro, já no formato que a tela de pedido lê.
  Future<Map<String, dynamic>> subject(OrderSubject which) async {
    if (!which.isCommand) return order(which.id);
    return commandAsSubject(await commandItems(which.id));
  }

  Future<Map<String, dynamic>> addSubjectItem({
    required OrderSubject to,
    required String productId,
    required String productName,
    required int quantity,
    String customerNote = '',
    List<String> addonIds = const [],
    String? variationId,
  }) => to.isCommand
      ? launchCommandItem(
          commandId: to.id,
          productId: productId,
          productName: productName,
          quantity: quantity,
          customerNote: customerNote,
          addonIds: addonIds,
          variationId: variationId,
        )
      : addItem(
          orderId: to.id,
          productId: productId,
          productName: productName,
          quantity: quantity,
          customerNote: customerNote,
          addonIds: addonIds,
          variationId: variationId,
        );

  Future<Map<String, dynamic>> voidSubjectItem({
    required OrderSubject of,
    required String itemId,
    required String itemLabel,
    required String reason,
  }) => of.isCommand
      ? voidCommandItem(
          commandId: of.id,
          itemId: itemId,
          itemLabel: itemLabel,
          reason: reason,
        )
      : voidItem(
          orderId: of.id,
          itemId: itemId,
          itemLabel: itemLabel,
          reason: reason,
        );

  Future<Map<String, dynamic>> sendSubjectToKitchen(OrderSubject which) =>
      which.isCommand
      ? sendCommandToKitchen(which.id)
      : sendToKitchen(which.id);
}
