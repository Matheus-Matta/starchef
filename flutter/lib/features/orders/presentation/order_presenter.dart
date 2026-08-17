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
    final localReference = '${order['_offline_queue_id'] ?? order['id'] ?? ''}'
        .replaceFirst('offline-', '');
    final referenceSuffix = localReference.length > 8
        ? localReference.substring(localReference.length - 8)
        : localReference;
    return {
      'sequence': referenceSuffix.isEmpty
          ? 'LOCAL'
          : 'LOCAL-${referenceSuffix.toUpperCase()}',
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
    final selectedVariationIds = (response['variations'] as List? ?? const [])
        .map((value) => value is Map ? '${value['id']}' : '$value')
        .toSet();
    final selectedAddonIds = (response['addons'] as List? ?? const [])
        .map((value) => value is Map ? '${value['id']}' : '$value')
        .toSet();
    final variations = (product['variations'] as List? ?? const [])
        .whereType<Map>()
        .where((value) => selectedVariationIds.contains('${value['id']}'))
        .map((value) => Map<String, dynamic>.from(value))
        .toList();
    final addons = (product['addons'] as List? ?? const [])
        .whereType<Map>()
        .where((value) => selectedAddonIds.contains('${value['id']}'))
        .map(
          (value) => {
            ...Map<String, dynamic>.from(value),
            'addon': value['id'],
            'addon_name': value['name'],
            'quantity': 1,
            'unit_price': value['price'],
            'total_price': ValueFormatters.number(value['price']) * quantity,
          },
        )
        .toList();
    final unitPrice = expectedUnitPrice(product, response: response);
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
      'variations': variations,
      'addons': addons,
    };
  }

  static double expectedUnitPrice(
    JsonMap product, {
    JsonMap? response,
    Iterable<String> variationIds = const [],
    Iterable<String> addonIds = const [],
  }) {
    final selectedVariations = {
      ...variationIds,
      ...(response?['variations'] as List? ?? const []).map(
        (value) => value is Map ? '${value['id']}' : '$value',
      ),
    };
    final selectedAddons = {
      ...addonIds,
      ...(response?['addons'] as List? ?? const []).map(
        (value) => value is Map ? '${value['id']}' : '$value',
      ),
    };
    var total = ValueFormatters.number(
      product['current_price'] ?? product['sale_price'],
    );
    for (final variation in (product['variations'] as List? ?? const [])) {
      if (variation is Map &&
          selectedVariations.contains('${variation['id']}')) {
        total += ValueFormatters.number(variation['price_delta']);
      }
    }
    for (final addon in (product['addons'] as List? ?? const [])) {
      if (addon is Map && selectedAddons.contains('${addon['id']}')) {
        total += ValueFormatters.number(addon['price']);
      }
    }
    return total;
  }

  static JsonMap sentToKitchen(JsonMap order) {
    final items = (order['items'] as List? ?? const [])
        .whereType<Map>()
        .map(
          (item) => item['status'] == 'pending'
              ? {...Map<String, dynamic>.from(item), 'status': 'sent'}
              : Map<String, dynamic>.from(item),
        )
        .toList();
    return {
      ...order,
      'items': items,
      'production_status': 'sent_to_kitchen',
      'updated_at': DateTime.now().toUtc().toIso8601String(),
    };
  }

  static JsonMap closeOfflineOrder(
    JsonMap order, {
    required bool serviceFeeEnabled,
    required double serviceFeePercent,
  }) {
    final subtotal = ValueFormatters.number(order['subtotal']);
    final fee = serviceFeeEnabled ? subtotal * serviceFeePercent / 100 : 0.0;
    final discount = ValueFormatters.number(order['discount']);
    final delivery = ValueFormatters.number(order['delivery_fee']);
    final total = (subtotal + fee + delivery - discount).clamp(
      0,
      double.infinity,
    );
    return {
      ...order,
      'service_fee_enabled': serviceFeeEnabled,
      'service_fee': fee.toStringAsFixed(2),
      'total': total.toStringAsFixed(2),
      'status': 'awaiting_payment',
      'updated_at': DateTime.now().toUtc().toIso8601String(),
      '_offline_pending': true,
    };
  }

  static JsonMap withItems(JsonMap order, List<JsonMap> items) {
    final subtotal = items.fold<double>(
      0,
      (total, item) => total + ValueFormatters.number(item['total_price']),
    );
    final serviceFee = order['service_fee_enabled'] == false
        ? 0.0
        : ValueFormatters.number(order['service_fee']);
    final delivery = ValueFormatters.number(order['delivery_fee']);
    final discount = ValueFormatters.number(order['discount']);
    final total = (subtotal + serviceFee + delivery - discount).clamp(
      0,
      double.infinity,
    );
    return {...order, 'items': items, 'subtotal': subtotal, 'total': total};
  }
}
