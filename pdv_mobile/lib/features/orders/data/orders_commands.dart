part of 'orders_repository.dart';

extension OrdersCommands on OrdersRepository {
  Future<Map<String, dynamic>> createOrder(String orderType) => _mutateCreate(
    path: '/orders/',
    summary: 'Novo pedido',
    body: {'order_type': orderType},
    optimisticFields: {'order_type': orderType},
  );

  Future<Map<String, dynamic>> createOrderWithItem({
    required String orderType,
    required String productId,
    required int quantity,
    required List<String> addonIds,
    String? variationId,
    String customerNote = '',
    String? commandId,
    String? tableId,
  }) {
    final item = {
      'product': productId,
      'quantity': quantity,
      'variations': variationId == null ? const [] : [variationId],
      'addons': addonIds,
      'customer_note': customerNote,
    };
    return _mutateCreate(
      path: '/orders/create-with-item/',
      summary: 'Novo pedido',
      body: {
        'order_type': orderType,
        'command': ?commandId,
        'table': ?tableId,
        'item': item,
      },
      optimisticFields: {
        'order_type': orderType,
        'command': ?commandId,
        'table': ?tableId,
        'items': [
          {...item, 'status': 'pending'},
        ],
      },
    );
  }

  Future<Map<String, dynamic>> _mutateCreate({
    required String path,
    required String summary,
    required Map<String, dynamic> body,
    required Map<String, dynamic> optimisticFields,
  }) async {
    final placeholderId = 'offline-${OperationId.random()}';
    try {
      return await gateway.mutate(
        method: 'POST',
        path: path,
        kind: 'create_order',
        summary: summary,
        body: body,
        placeholderOrderId: placeholderId,
      );
    } on MutationQueued {
      return {
        'id': placeholderId,
        '_offline_pending': true,
        'status': 'open',
        'payment_status': 'pending',
        'items': const [],
        ...optimisticFields,
      };
    }
  }

  Future<Map<String, dynamic>> linkTable({
    required String commandId,
    required String tableId,
    required String tableLabel,
  }) => mutate(
    method: 'POST',
    path: '/commands/$commandId/link-table/',
    kind: 'link_table',
    summary: 'Vincular à mesa $tableLabel',
    body: {'table_id': tableId},
  );

  Future<Map<String, dynamic>> unlinkTable({required String commandId}) =>
      mutate(
        method: 'POST',
        path: '/commands/$commandId/unlink-table/',
        kind: 'unlink_table',
        summary: 'Desvincular comanda da mesa',
      );

  Future<Map<String, dynamic>> addItem({
    required String orderId,
    required String productId,
    required String productName,
    required int quantity,
    String customerNote = '',
    List<String> addonIds = const [],
    String? variationId,
    Map<String, String>? metafields,
  }) => mutate(
    method: 'POST',
    path: '/orders/$orderId/items/',
    kind: 'add_item',
    summary: '${quantity}x $productName',
    body: {
      'product': productId,
      'quantity': quantity,
      'variations': variationId == null ? const [] : [variationId],
      'addons': addonIds,
      'customer_note': customerNote,
      // O CODIGO DE QUEM LANCOU viaja com o ITEM, e por isso sobrevive a fila
      // offline: a operacao enfileirada sobe horas depois, quando quem lancou
      // pode nem estar mais no turno.
      'metafields': ?metafields,
    },
  );

  Future<Map<String, dynamic>> voidItem({
    required String orderId,
    required String itemId,
    required String itemLabel,
    required String reason,
  }) => mutate(
    method: 'DELETE',
    path: '/orders/$orderId/items/$itemId/void/',
    kind: 'void_item',
    summary: 'Cancelar $itemLabel',
    body: {'reason': reason},
  );

  Future<Map<String, dynamic>> pay({
    required String orderId,
    required String paymentMethodId,
    required String amount,
    String cardSubtype = '',
    String? cashRegisterId,
    String reference = '',
  }) => mutate(
    method: 'POST',
    path: '/orders/$orderId/pay/',
    kind: 'pay_order',
    summary: 'Receber $amount',
    body: {
      'payment_method': paymentMethodId,
      'amount': amount,
      'cash_register': ?cashRegisterId,
      'client_payment_id': 'mobile-${OperationId.random()}',
      'metadata': {
        'card_subtype': cardSubtype,
        'reference': reference,
        'source': 'pdv_mobile',
      },
    },
  );

  Future<Map<String, dynamic>> sendToKitchen(String orderId) => mutate(
    method: 'POST',
    path: '/orders/$orderId/send-to-kitchen/',
    kind: 'send_to_kitchen',
    summary: 'Enviar pedido para a cozinha',
  );
}
