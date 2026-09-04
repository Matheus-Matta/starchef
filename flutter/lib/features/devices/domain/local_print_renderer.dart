import '../../../core/formatters/value_formatters.dart';
import '../../orders/presentation/order_presenter.dart';

typedef JsonMap = Map<String, dynamic>;

/// Cupons montados **no terminal**, sem o backend.
///
/// O PDV precisa imprimir com a internet desligada (§30), e quem renderiza os
/// cupons é o backend (`apps/printers/services.py`). A comanda de cozinha já
/// tinha um equivalente local em [OrderPresenter]; faltavam o recibo do
/// cliente, o cupom de cancelamento e a nota de teste — sem eles, uma queda de
/// rede deixava o cliente sem comprovante e a cozinha sem aviso de item
/// cancelado.
///
/// **Este arquivo espelha `apps/printers/services.py`.** As larguras, a ordem
/// das linhas e o alinhamento do valor são os mesmos de propósito: o mesmo
/// pedido impresso online e offline tem que sair igual no papel. Se o cupom do
/// backend mudar, este muda junto.
abstract final class LocalPrintRenderer {
  /// `LARGURA_CUPOM` no backend: 80 mm em fonte monoespaçada.
  static const receiptWidth = 42;

  /// `_COLUNA_VALOR`: a coluna à direita onde o valor é alinhado.
  static const _amountColumn = 14;

  /// `LARGURA_COMANDA`: a comanda de cozinha usa bobina de 58 mm.
  static const ticketWidth = 32;

  /// Recibo de venda do cliente — espelha `_customer_receipt_text`.
  static String customerReceipt({
    required JsonMap order,
    required JsonMap? restaurant,
    required List<JsonMap> payments,
    JsonMap? table,
    JsonMap? command,
    JsonMap? customer,
    String operatorName = '',
    DateTime? now,
  }) {
    final info = _establishmentInfo(restaurant);
    final lines = <String>[
      _center(info.tradeName.toUpperCase(), receiptWidth),
      _center('RECIBO DE VENDA - NAO E DOCUMENTO FISCAL', receiptWidth),
    ];

    var document = 'CNPJ: ${info.cnpj.isEmpty ? '-' : info.cnpj}';
    if (info.stateRegistration.isNotEmpty) {
      document += ' - IE: ${info.stateRegistration}';
    }
    lines.add(_clip(document, receiptWidth));

    var address = '${info.address} ${info.city}'.trim();
    if (info.state.isNotEmpty) address += '/${info.state}';
    if (info.zipCode.isNotEmpty) address += ' - CEP ${info.zipCode}';
    if (address.isNotEmpty) lines.add(_clip(address, receiptWidth));
    if (info.phone.isNotEmpty) {
      lines.add(_clip('Telefone: ${info.phone}', receiptWidth));
    }

    lines
      ..add('-' * receiptWidth)
      ..add('Pedido nº ${order['sequence'] ?? ''}')
      ..addAll(
        orderContextLines(
          order,
          table: table,
          command: command,
          customer: customer,
        ),
      );
    if (operatorName.trim().isNotEmpty) {
      lines.add(_clip('Operador: ${operatorName.trim()}', receiptWidth));
    }
    lines
      ..add('Data: ${_dateTime(_openedAt(order, now))}')
      ..add('-' * receiptWidth);

    for (final item in _activeItems(order)) {
      // Produto por peso resolve tudo em uma linha só: repetir a quantidade
      // numa segunda linha mostraria o mesmo peso duas vezes.
      final description = _isWeighed(item)
          ? '${_quantity(item['quantity'])} x ${item['product_name']}'
                '${OrderPresenter.variationSuffix(item)} '
                '${_money(item['unit_price'])}/kg'
          : '${_quantity(item['quantity'])} x ${item['product_name']}'
                '${OrderPresenter.variationSuffix(item)}';
      lines.add(_amountLine(description, item['total_price']));
      // O adicional é uma composição da linha acima, não outro item: entra
      // indentado, sem repetir a quantidade, como detalhamento.
      for (final addon in (item['addons'] as List? ?? const [])) {
        if (addon is! Map) continue;
        lines.add(
          _amountLine('  ${addon['addon_name'] ?? addon['name']}',
              addon['total_price']),
        );
      }
    }

    lines
      ..add('-' * receiptWidth)
      ..add(_amountLine('Subtotal', order['subtotal']))
      ..add(_amountLine('Serviço', order['service_fee']))
      ..add(_amountLine('Desconto', order['discount']))
      ..add(_amountLine('Entrega', order['delivery_fee']))
      ..add(_amountLine('TOTAL', order['total']));

    if (payments.isNotEmpty) {
      lines
        ..add('-' * receiptWidth)
        ..add('FORMA(S) DE PAGAMENTO');
      for (final payment in payments) {
        lines.add(
          _amountLine(
            '${payment['payment_method_name'] ?? payment['payment_method'] ?? 'Pagamento'}',
            payment['amount'],
          ),
        );
        if (ValueFormatters.number(payment['change_amount']) > 0) {
          lines.add(_amountLine('Troco', payment['change_amount']));
        }
      }
    }

    final barcode = commandBarcode(order, command);
    if (barcode.isNotEmpty) {
      // Só o valor: o `LocalDeviceAgent` reconhece este payload e imprime o
      // Code128 de verdade; aqui cabe a legenda legível, redundante em
      // impressoras sem ESC/POS.
      lines
        ..add('-' * receiptWidth)
        ..add(_center('COMANDA - CODE128', receiptWidth))
        ..add(_center(barcode, receiptWidth));
    }

    lines
      ..add('-' * receiptWidth)
      ..add(_center('Obrigado pela preferência!', receiptWidth))
      ..add('');
    return lines.join('\n');
  }

  /// Cupom de cancelamento — espelha `_kitchen_cancellation_text`.
  ///
  /// É o que a cozinha precisa para tirar o item da fila. Sem ele impresso, o
  /// prato continua sendo feito depois de o cliente desistir.
  static String cancellationTicket({
    required JsonMap order,
    required JsonMap item,
    required String reason,
    String originalSerial = '-',
    String batchSerial = '-',
    JsonMap? table,
    JsonMap? command,
    String operatorName = '',
    DateTime? now,
  }) {
    final type = _orderTypeLabel('${order['order_type'] ?? ''}');
    final lines = <String>[
      _center('CANCELAMENTO', ticketWidth),
      _center('PEDIDO #${order['sequence'] ?? ''}', ticketWidth),
      _center('ORIGINAL $originalSerial', ticketWidth),
      _center('RODADA $batchSerial', ticketWidth),
      '-' * ticketWidth,
      _clip('TIPO: $type', ticketWidth),
    ];
    final tableNumber = table?['number'] ?? order['table_number'];
    if (tableNumber != null) {
      lines.add(_clip('MESA: $tableNumber', ticketWidth));
    }
    final commandCode = command?['code'] ?? order['command_code'];
    if (commandCode != null) {
      lines.add(_clip('COMANDA: $commandCode', ticketWidth));
    }
    lines.add(
      _clip(
        'CANCELAR ${_quantity(item['quantity'])}x ${item['product_name']}'
        '${OrderPresenter.variationSuffix(item)}',
        ticketWidth,
      ),
    );
    for (final addon in (item['addons'] as List? ?? const [])) {
      if (addon is! Map) continue;
      lines.add(_clip('  ${addon['addon_name'] ?? addon['name']}', ticketWidth));
    }
    lines.add(_clip('MOTIVO: $reason', ticketWidth));
    if (operatorName.trim().isNotEmpty) {
      lines.add(_clip('SOLICITADO POR: ${operatorName.trim()}', ticketWidth));
    }
    lines
      ..add(_dateTimeWithSeconds(now ?? DateTime.now()))
      ..add('-' * ticketWidth)
      ..add(_center('FIM DO CANCELAMENTO', ticketWidth))
      ..add('');
    return lines.join('\n');
  }

  /// Nota de pesagem — espelha `_weigh_ticket_text`.
  ///
  /// É o comprovante que o cliente leva do buffet até o caixa. Sem uma versão
  /// local, uma queda de rede deixava a balança pesando e ninguém conseguindo
  /// cobrar: o prato ia para a mesa sem papel nenhum.
  static String weighTicket({
    required JsonMap order,
    required JsonMap? restaurant,
    JsonMap? table,
    JsonMap? command,
    DateTime? now,
  }) {
    final info = _establishmentInfo(restaurant);
    final where = (table?['number'] ?? order['table_number']) != null
        ? 'Mesa ${table?['number'] ?? order['table_number']}'
        : (command?['code'] ?? order['command_code']) != null
        ? 'Comanda ${command?['code'] ?? order['command_code']}'
        : 'Balcao';

    final lines = <String>[
      ..._establishmentLines(info),
      _center('NOTA DE PESAGEM', receiptWidth),
      '-' * receiptWidth,
      'Pedido #${order['sequence'] ?? ''}  $where',
      _dateTime(now ?? DateTime.now()),
      '-' * receiptWidth,
    ];

    for (final item in _activeItems(order)) {
      lines.add(
        _amountLine(
          '${item['product_name']}${OrderPresenter.variationSuffix(item)}',
          item['total_price'],
        ),
      );
      if (_isWeighed(item)) {
        lines.add(
          '${ValueFormatters.number(item['quantity']).toStringAsFixed(3)} kg x '
          'R\$ ${_money(item['unit_price'])}/kg',
        );
      } else {
        lines.add(
          '${_quantity(item['quantity'])} un x R\$ ${_money(item['unit_price'])}',
        );
      }
      for (final addon in (item['addons'] as List? ?? const [])) {
        if (addon is! Map) continue;
        lines.add(
          _amountLine('  ${addon['addon_name'] ?? addon['name']}',
              addon['total_price']),
        );
      }
      lines.add('-' * receiptWidth);
    }

    lines.add(_amountLine('TOTAL DO PEDIDO', order['total']));
    final barcode = commandBarcode(order, command);
    if (barcode.isNotEmpty) {
      lines
        ..add('')
        ..add(_center('COMANDA - CODE128', receiptWidth))
        ..add(_center(barcode, receiptWidth));
    }
    lines
      ..add('')
      ..add(_center('Pague no caixa. Obrigado!', receiptWidth));
    return lines.join('\n');
  }

  /// Cabeçalho do estabelecimento — espelha `_establishment_lines`.
  static List<String> _establishmentLines(_Establishment info) {
    final lines = <String>[
      _center(info.tradeName, receiptWidth),
      'CNPJ: ${info.cnpj.isEmpty ? '-' : info.cnpj}',
    ];
    if (info.stateRegistration.isNotEmpty) {
      lines.add(_clip('IE: ${info.stateRegistration}', receiptWidth));
    }
    final address = '${info.address} ${info.city}/${info.state}'
        .replaceAll(RegExp(r'^[\s/]+|[\s/]+$'), '');
    if (address.isNotEmpty) lines.add(_clip(address, receiptWidth));
    if (info.zipCode.isNotEmpty) {
      lines.add(_clip('CEP: ${info.zipCode}', receiptWidth));
    }
    if (info.phone.isNotEmpty) {
      lines.add(_clip('Tel: ${info.phone}', receiptWidth));
    }
    return lines;
  }

  /// Nota de teste de impressora — espelha `register_printer_test_job`.
  static String printerTest({required JsonMap printer, DateTime? now}) {
    final sector = printer['sector_name'] ?? 'Todos os setores';
    final lines = <String>[
      _center('STARCHEF PDV', ticketWidth),
      _center('TESTE DE IMPRESSORA', ticketWidth),
      '-' * ticketWidth,
      'Nome: ${printer['name'] ?? ''}',
      'Driver: ${printer['driver_type'] ?? ''}',
      'Conexao: ${printer['connection_type'] ?? ''}',
      'Windows/Serial: ${_orDefault(printer['endpoint'], 'Nao configurado')}',
      'IP: ${_orDefault(printer['host'], 'Nao configurado')}',
      'Porta TCP: ${printer['port'] ?? ''}',
      'Timeout: ${printer['timeout_seconds'] ?? ''}s',
      'Setor: $sector',
      'Impressao automatica: '
          '${printer['auto_print'] == true ? 'Ativada' : 'Desativada'}',
      'Status: ${printer['is_active'] == false ? 'Inativa' : 'Ativa'}',
      '-' * ticketWidth,
      _dateTimeWithSeconds(now ?? DateTime.now()),
      _center('CONEXAO REALIZADA', ticketWidth),
      '',
    ];
    return lines.join('\n');
  }

  /// Linhas que identificam o pedido — espelha `_order_context_lines`.
  ///
  /// Mesa e comanda só fazem sentido no salão; balcão, retirada e delivery
  /// mostravam "Mesa: - Comanda: -", que não diz nada sobre o pedido e ainda
  /// escondia para quem era a entrega.
  static List<String> orderContextLines(
    JsonMap order, {
    JsonMap? table,
    JsonMap? command,
    JsonMap? customer,
    int width = receiptWidth,
  }) {
    final type = '${order['order_type'] ?? ''}';
    final customerName =
        '${customer?['name'] ?? order['customer_name'] ?? ''}'.trim();
    final customerPhone =
        '${customer?['phone'] ?? order['customer_phone'] ?? ''}'.trim();

    if (type == 'delivery') {
      return [
        'DELIVERY',
        if (customerName.isNotEmpty) _clip('Cliente: $customerName', width),
        if (customerPhone.isNotEmpty) _clip('Telefone: $customerPhone', width),
        ..._deliveryAddressLines(order, width),
      ];
    }
    if (type == 'takeaway') {
      return [
        'RETIRADA',
        if (customerName.isNotEmpty) _clip('Cliente: $customerName', width),
        if (customerPhone.isNotEmpty) _clip('Telefone: $customerPhone', width),
      ];
    }
    if (type == 'counter') {
      return [
        'BALCAO',
        if (customerName.isNotEmpty) _clip('Cliente: $customerName', width),
      ];
    }
    final tableNumber = table?['number'] ?? order['table_number'];
    final commandCode = command?['code'] ?? order['command_code'];
    final tablePart = tableNumber == null ? null : 'Mesa: $tableNumber';
    final commandPart = commandCode == null ? null : 'Comanda: $commandCode';
    if (tablePart != null && commandPart != null) {
      return [_clip('$tablePart - $commandPart', width)];
    }
    if (tablePart != null) return [tablePart];
    if (commandPart != null) return [commandPart];
    return ['Mesa: - Comanda: -'];
  }

  /// Código de barras da comanda, quando o pedido está vinculado a uma.
  static String commandBarcode(JsonMap order, JsonMap? command) =>
      '${command?['code'] ?? order['command_code'] ?? command?['number'] ?? order['command_number'] ?? ''}';

  // ------------------------------------------------------------- formatação

  static List<String> _deliveryAddressLines(JsonMap order, int width) {
    final address = order['delivery_address'];
    if (address is! Map) return const [];
    final lines = <String>[];
    var street = '${address['street'] ?? ''}, ${address['number'] ?? ''}';
    street = street.replaceAll(RegExp(r'^,\s*|,\s*$'), '').trim();
    final complement = '${address['complement'] ?? ''}'.trim();
    if (complement.isNotEmpty) street += ' - $complement';
    if (street.isNotEmpty) lines.add(_clip(street, width));
    final district =
        '${address['district'] ?? ''} - ${address['city'] ?? ''}/${address['state'] ?? ''}'
            .replaceAll(RegExp(r'^\s*-\s*|\s*-\s*$'), '')
            .trim();
    if (district.isNotEmpty) lines.add(_clip(district, width));
    final reference = '${address['reference'] ?? ''}'.trim();
    if (reference.isNotEmpty) lines.add(_clip('Ref: $reference', width));
    return lines;
  }

  static _Establishment _establishmentInfo(JsonMap? restaurant) {
    String pick(String field) => '${restaurant?[field] ?? ''}'.trim();
    return _Establishment(
      tradeName: pick('trade_name').isEmpty
          ? pick('legal_name')
          : pick('trade_name'),
      cnpj: pick('cnpj'),
      stateRegistration: pick('state_registration'),
      phone: pick('phone'),
      address: pick('address'),
      city: pick('city'),
      state: pick('state'),
      zipCode: pick('zip_code'),
    );
  }

  static List<JsonMap> _activeItems(JsonMap order) =>
      (order['items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .where((item) => !{'cancelled', 'voided'}.contains('${item['status']}'))
          .toList();

  static bool _isWeighed(JsonMap item) =>
      item['product_is_weighed'] == true || '${item['pricing_unit']}' == 'kg';

  /// Rótulo à esquerda, valor em reais à direita — espelha `_linha_valor`.
  static String _amountLine(String label, Object? value) {
    final amount = 'R\$ ${_money(value)}';
    final labelWidth = receiptWidth - _amountColumn;
    final left = label.length > labelWidth
        ? label.substring(0, labelWidth)
        : label.padRight(labelWidth);
    return '$left${amount.padLeft(_amountColumn)}';
  }

  static String _money(Object? value) =>
      ValueFormatters.number(value).toStringAsFixed(2);

  /// Formato `:g` do Python: sem casas desnecessárias.
  static String _quantity(Object? value) {
    final number = ValueFormatters.number(value);
    if (number == number.roundToDouble()) return number.toInt().toString();
    var text = number.toStringAsFixed(3);
    while (text.endsWith('0')) {
      text = text.substring(0, text.length - 1);
    }
    return text.endsWith('.') ? text.substring(0, text.length - 1) : text;
  }

  static DateTime _openedAt(JsonMap order, DateTime? fallback) =>
      DateTime.tryParse('${order['opened_at'] ?? order['created_at'] ?? ''}')
          ?.toLocal() ??
      fallback ??
      DateTime.now();

  static String _dateTime(DateTime value) {
    String two(int number) => number.toString().padLeft(2, '0');
    return '${two(value.day)}/${two(value.month)}/${value.year} '
        '${two(value.hour)}:${two(value.minute)}';
  }

  static String _dateTimeWithSeconds(DateTime value) {
    String two(int number) => number.toString().padLeft(2, '0');
    return '${two(value.day)}/${two(value.month)}/${value.year} '
        '${two(value.hour)}:${two(value.minute)}:${two(value.second)}';
  }

  static String _orDefault(Object? value, String fallback) {
    final text = '${value ?? ''}'.trim();
    return text.isEmpty ? fallback : text;
  }

  static String _clip(String value, int width) =>
      value.length > width ? value.substring(0, width) : value;

  static String _center(String text, int width) {
    if (text.length >= width) return _clip(text, width);
    final padding = width - text.length;
    final left = padding ~/ 2;
    return '${' ' * left}$text${' ' * (padding - left)}';
  }

  /// `TIPO_ATENDIMENTO_COMANDA` no backend: os rótulos do modelo são em
  /// inglês e sairiam "TABLE" no papel.
  static String _orderTypeLabel(String value) =>
      const {
        'table': 'MESA',
        'command': 'COMANDA',
        'counter': 'BALCAO',
        'delivery': 'DELIVERY',
        'takeaway': 'RETIRADA',
      }[value] ??
      value.toUpperCase();
}

class _Establishment {
  const _Establishment({
    required this.tradeName,
    required this.cnpj,
    required this.stateRegistration,
    required this.phone,
    required this.address,
    required this.city,
    required this.state,
    required this.zipCode,
  });

  final String tradeName;
  final String cnpj;
  final String stateRegistration;
  final String phone;
  final String address;
  final String city;
  final String state;
  final String zipCode;
}
