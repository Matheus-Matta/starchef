import '../../../core/formatters/value_formatters.dart';

typedef JsonMap = Map<String, dynamic>;

/// Regras de apresentação de um pedido local/offline.
///
/// Mantém cálculos e preenchimento de defaults fora dos widgets. A API segue
/// como fonte final; estes valores permitem operar até a sincronização.
abstract final class OrderPresenter {
  static bool isOffline(JsonMap? value) =>
      value?['_offline_pending'] == true ||
      '${value?['id'] ?? ''}'.startsWith('offline-');

  static JsonMap completeOfflineOrder(
    JsonMap order, {
    required String? restaurantId,
    required String type,
    JsonMap? table,
    JsonMap? command,
  }) {
    if (!isOffline(order)) return order;
    return {
      'sequence': 'OFFLINE',
      'restaurant': restaurantId,
      'order_type': type,
      'status': 'open',
      'payment_status': 'pending',
      'production_status': 'idle',
      'subtotal': '0.00',
      'service_fee': '0.00',
      'discount': '0.00',
      'total': '0.00',
      'items': <JsonMap>[],
      if (table != null) 'table': table['id'],
      if (table != null) 'table_number': table['number'],
      // Sem isso o cabeçalho do pedido offline por comanda não sabe dizer
      // qual comanda foi aberta — e é justamente o que o operador confere.
      if (command != null) 'command': command['id'],
      if (command != null) 'command_code': command['code'],
      if (command != null) 'command_number': command['number'],
      ...order,
    };
  }

  static JsonMap offlineItem({
    required JsonMap response,
    required JsonMap product,
    required double quantity,
    String customerNote = '',
  }) {
    final unitPrice = ValueFormatters.number(
      product['current_price'] ?? product['sale_price'],
    );
    return {
      ...response,
      'product': product['id'],
      'product_name': product['name'],
      'pricing_unit': product['pricing_unit'] ?? 'unit',
      'quantity': quantity,
      'unit_price': unitPrice,
      'total_price': unitPrice * quantity,
      'status': 'pending',
      'customer_note': customerNote,
      'addons': <JsonMap>[],
    };
  }

  static JsonMap withItems(JsonMap order, List<JsonMap> items) {
    final subtotal = items.fold<double>(
      0,
      (total, item) => total + ValueFormatters.number(item['total_price']),
    );
    return {...order, 'items': items, 'subtotal': subtotal, 'total': subtotal};
  }
}
