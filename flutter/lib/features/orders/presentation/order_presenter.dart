import 'dart:math';

import '../../../core/formatters/value_formatters.dart';

typedef JsonMap = Map<String, dynamic>;

/// Uma comanda de cozinha pronta para `LocalDeviceAgent.printForPrinter`.
class KitchenTicket {
  const KitchenTicket({required this.printer, required this.text});

  final JsonMap printer;
  final String text;
}

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
    // Arredonda a taxa isoladamente, como o backend faz ao gravar, para que o
    // total previsto aqui bata com o total recalculado no fechamento — do
    // contrário o servidor rejeitava o fechamento por divergência de total.
    final rawFee = serviceFeeEnabled ? subtotal * serviceFeePercent / 100 : 0.0;
    final fee = double.parse(rawFee.toStringAsFixed(2));
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

  /// Referência da rodada de produção, gerada no terminal quando a rede está
  /// fora — o backend usa este valor como `OrderBatch.serial` (em vez de
  /// sortear um) para que o `REF:` já impresso na comanda offline bata com o
  /// registro criado quando a fila sincronizar.
  static String generateBatchSerial() {
    final bytes = List<int>.generate(16, (_) => Random.secure().nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    String hex(int start, int end) => bytes
        .sublist(start, end)
        .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
        .join();
    return '${hex(0, 4)}-${hex(4, 6)}-${hex(6, 8)}-${hex(8, 10)}-${hex(10, 16)}';
  }

  /// Monta uma comanda por combinação setor×impressora ativa, espelhando
  /// `register_kitchen_batch_print_jobs`/`_kitchen_ticket_text`
  /// (`backend/apps/printers/services.py:345-396`) — inclusive os "pulos
  /// silenciosos": item sem setor no produto, ou setor sem impressora ativa,
  /// simplesmente não geram ticket, sem erro. Só é chamado quando a rede caiu
  /// e a impressão não pode esperar o backend renderizar o `PrintJob`.
  static List<KitchenTicket> buildOfflineKitchenTickets({
    required JsonMap? table,
    required JsonMap? command,
    required List<JsonMap> pendingItems,
    required List<JsonMap> products,
    required List<JsonMap> printers,
    required String batchSerial,
  }) {
    final productsById = {
      for (final product in products) '${product['id']}': product,
    };
    final itemsBySector = <String, List<JsonMap>>{};
    for (final item in pendingItems) {
      final product = productsById['${item['product']}'];
      final sector = product?['sector'];
      if (sector == null) continue;
      itemsBySector.putIfAbsent('$sector', () => []).add(item);
    }
    if (itemsBySector.isEmpty) return const [];

    final tickets = <KitchenTicket>[];
    for (final entry in itemsBySector.entries) {
      final sectorPrinters = printers.where(
        (printer) =>
            printer['is_active'] != false &&
            '${printer['sector'] ?? ''}' == entry.key,
      );
      if (sectorPrinters.isEmpty) continue;
      final text = _kitchenTicketText(
        table: table,
        command: command,
        items: entry.value,
        batchSerial: batchSerial,
      );
      for (final printer in sectorPrinters) {
        tickets.add(KitchenTicket(printer: printer, text: text));
      }
    }
    return tickets;
  }

  static String _kitchenTicketText({
    required JsonMap? table,
    required JsonMap? command,
    required List<JsonMap> items,
    required String batchSerial,
  }) {
    String clip(String value) => value.length > 32 ? value.substring(0, 32) : value;
    const separator = '--------------------------------';
    final lines = <String>[clip(_center('NOVO PEDIDO', 32)), separator];
    if (table != null) lines.add(clip('MESA: ${table['number']}'));
    if (command != null) lines.add(clip('COMANDA: ${command['code']}'));
    if (table != null || command != null) lines.add(separator);
    for (final item in items) {
      final quantity = _formatQuantity(item['quantity']);
      lines.add(clip('${quantity}x ${item['product_name']}'));
      for (final variation in (item['variations'] as List? ?? const [])) {
        final name = variation is Map ? variation['name'] : variation;
        lines.add(clip('  VAR: $name'));
      }
      for (final addon in (item['addons'] as List? ?? const [])) {
        if (addon is! Map) continue;
        final addonQuantity = _formatQuantity(addon['quantity']);
        lines.add(clip('  + ${addonQuantity}x ${addon['addon_name']}'));
      }
      final note = '${item['customer_note'] ?? ''}';
      if (note.isNotEmpty) lines.add(clip('  OBS: $note'));
      lines.add(separator);
    }
    lines.addAll(['REF: $batchSerial', '']);
    return lines.join('\n');
  }

  static String _center(String text, int width) {
    if (text.length >= width) return text;
    final padding = width - text.length;
    final left = padding ~/ 2;
    return '${' ' * left}$text${' ' * (padding - left)}';
  }

  static String _formatQuantity(dynamic value) {
    final number = ValueFormatters.number(value);
    if (number == number.roundToDouble()) return number.toInt().toString();
    var text = number.toStringAsFixed(3);
    while (text.endsWith('0')) {
      text = text.substring(0, text.length - 1);
    }
    return text.endsWith('.') ? text.substring(0, text.length - 1) : text;
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
