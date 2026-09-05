import 'dart:math';

import '../../../core/formatters/value_formatters.dart';

typedef JsonMap = Map<String, dynamic>;

/// Uma comanda de cozinha pronta para uma impressora.
class KitchenTicket {
  const KitchenTicket({required this.printer, required this.text});

  final JsonMap printer;
  final String text;
}

/// O resultado do roteamento por setor: as comandas a imprimir **e por que**
/// alguma coisa ficou de fora.
///
/// O roteamento é silencioso por natureza — item sem setor e setor sem
/// impressora simplesmente não geram papel, do mesmo jeito que no backend. Sem
/// registrar o motivo, "a comanda não saiu e não deu erro" só se investigava
/// abrindo o banco. Esta classe carrega o diagnóstico junto com o resultado,
/// para quem chama registrar em uma linha.
class KitchenTicketPlan {
  const KitchenTicketPlan({
    required this.tickets,
    required this.printersConsidered,
    required this.itemsBySector,
    required this.productsWithoutSector,
    required this.sectorsWithoutPrinter,
  });

  static const empty = KitchenTicketPlan(
    tickets: [],
    printersConsidered: 0,
    itemsBySector: {},
    productsWithoutSector: [],
    sectorsWithoutPrinter: [],
  );

  final List<KitchenTicket> tickets;

  /// Quantas impressoras entraram na decisão (a lista que o terminal conhece).
  final int printersConsidered;

  /// Quantos itens caíram em cada setor.
  final Map<String, int> itemsBySector;

  /// Produtos cujo item não pôde ser roteado: sem setor cadastrado, ou fora
  /// do catálogo carregado neste terminal — nos dois casos o item some da
  /// comanda sem nenhum aviso.
  final List<String> productsWithoutSector;

  /// Setores com item para produzir e nenhuma impressora ativa apontando
  /// para eles.
  final List<String> sectorsWithoutPrinter;

  bool get isEmpty => tickets.isEmpty;

  /// Linha única para o log do terminal.
  Map<String, Object?> toLog() => {
    'comandas': tickets.length,
    'impressoras_conhecidas': printersConsidered,
    'itens_por_setor': itemsBySector,
    'produtos_sem_setor': productsWithoutSector,
    'setores_sem_impressora': sectorsWithoutPrinter,
    'destinos': [
      for (final ticket in tickets)
        {
          'impressora': '${ticket.printer['name'] ?? ticket.printer['id']}',
          'setor': '${ticket.printer['sector'] ?? ''}',
        },
    ],
  };
}

/// Regras de apresentação de um pedido local/offline.
///
/// Mantém cálculos e preenchimento de defaults fora dos widgets. A API segue
/// como fonte final; estes valores permitem operar até a sincronização.
abstract final class OrderPresenter {
  /// Monta um recebimento que ainda NÃO foi enviado ao servidor.
  ///
  /// Fica aqui, e não na tela, porque é a conta que decide quando o botão de
  /// concluir libera: só o valor APLICADO abate o pedido, e o excedente em
  /// dinheiro é troco. É a mesma conta que o servidor refaz ao receber — se as
  /// duas divergirem, o caixa fecha uma venda que o servidor considera em
  /// aberto (ou o contrário).
  ///
  /// Cartão e outros meios não podem passar do restante: quem valida isso é a
  /// tela, porque ela é quem tem como avisar o operador.
  static JsonMap stagedPayment({
    required String localId,
    required JsonMap method,
    required double received,
    required double remaining,
  }) {
    final isCash = method['method_type'] == 'cash';
    final applied = isCash && received > remaining ? remaining : received;
    return {
      '_staged': true,
      'id': localId,
      'payment_method_name': '${method['name'] ?? 'Pagamento'}',
      'method_type': method['method_type'],
      'amount': applied,
      'change_amount': received - applied,
      '_staged_method': method,
    };
  }

  /// Quem e este pedido, em uma linha: contexto, itens e total.
  ///
  /// Mora na BARRA DO APLICATIVO. Ja foi um bloco dentro do painel do pedido e
  /// outro dentro da tela de pagamento, os dois repetindo o que a barra logo
  /// acima ja dizia pela metade — e cada um com a sua propria versao do
  /// contexto, que e a parte que tem regra de verdade: comanda manda em mesa,
  /// mesa manda em cliente, e uma comanda sem cliente nem mesa e self-service.
  ///
  /// Fica aqui, e nao na tela, porque essa regra e a unica parte da barra que
  /// vale a pena provar com teste.
  static String headerSubtitle({
    required JsonMap order,
    required int itemCount,
    required String Function(dynamic) money,
    JsonMap? table,
    JsonMap? command,
    double? remaining,
  }) {
    final partes = <String>[];
    final customerName = '${order['customer_name'] ?? ''}'.trim();
    if (command != null) {
      final name = '${command['customer_name'] ?? ''}'.trim();
      partes.add('Comanda ${command['number']}');
      if (table != null) partes.add('Mesa ${table['number']}');
      if (name.isNotEmpty) {
        partes.add(name);
      } else if (table == null) {
        partes.add('Self-service');
      }
    } else if (table != null) {
      partes.add('Mesa ${table['number']}');
    } else if (customerName.isNotEmpty) {
      partes.add(customerName);
    } else {
      partes.add(orderTypeLabel('${order['order_type'] ?? ''}'));
    }

    partes.add(itemCount == 1 ? '1 item' : '$itemCount itens');
    partes.add(money(order['total']));
    // No pagamento, o que o operador olha o tempo todo e o que ainda falta.
    if (remaining != null && remaining > .009) {
      partes.add('Falta ${money(remaining)}');
    }
    return partes.join('  ·  ');
  }

  static String orderTypeLabel(String value) =>
      const {
        'command': 'Comanda',
        'table': 'Mesa',
        'counter': 'Balcao',
        'takeaway': 'Retirada',
        'delivery': 'Delivery',
      }[value] ??
      'Pedido';

  /// Le um valor DIGITADO no campo de pagamento como o teclado da tela le.
  ///
  /// Devolve a mesma cadeia de digitos que as teclas montam: os digitos entram
  /// pela direita e os dois ultimos sao os centavos. Ler o texto como um
  /// decimal comum daria ao campo um comportamento e ao teclado outro, e "12"
  /// significaria R$ 0,12 ou R$ 12,00 dependendo de por onde o operador tivesse
  /// entrado com o valor.
  ///
  /// O teto de nove digitos e o mesmo das teclas: acima disso nao existe venda,
  /// existe engano de dedo.
  static String typedPaymentDigits(String raw) {
    final digitos = raw
        .replaceAll(RegExp(r'[^0-9]'), '')
        .replaceFirst(RegExp(r'^0+(?=\d)'), '');
    if (digitos.isEmpty) return '0';
    return digitos.length > 9 ? digitos.substring(0, 9) : digitos;
  }

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
  static KitchenTicketPlan buildOfflineKitchenTickets({
    required JsonMap? order,
    required JsonMap? table,
    required JsonMap? command,
    required List<JsonMap> pendingItems,
    required List<JsonMap> products,
    required List<JsonMap> printers,
    required String batchSerial,
    String operatorName = '',
    DateTime? now,
  }) {
    // O relógio é lido UMA vez: duas impressoras do mesmo setor recebem a
    // mesma rodada, e reler a hora por comanda fazia os dois papéis saírem
    // com horários diferentes quando o segundo virava no meio do laço.
    final printedAt = now ?? DateTime.now();
    final productsById = {
      for (final product in products) '${product['id']}': product,
    };
    final itemsBySector = <String, List<JsonMap>>{};
    final productsWithoutSector = <String>[];
    for (final item in pendingItems) {
      final product = productsById['${item['product']}'];
      final sector = product?['sector'];
      if (sector == null) {
        // Produto sem setor OU produto que não está no catálogo carregado
        // aqui: os dois somem da comanda sem aviso, e só o registro distingue
        // um do outro na hora de investigar.
        productsWithoutSector.add('${item['product']}');
        continue;
      }
      itemsBySector.putIfAbsent('$sector', () => []).add(item);
    }
    final sectorCounts = {
      for (final entry in itemsBySector.entries) entry.key: entry.value.length,
    };
    if (itemsBySector.isEmpty) {
      return KitchenTicketPlan(
        tickets: const [],
        printersConsidered: printers.length,
        itemsBySector: sectorCounts,
        productsWithoutSector: productsWithoutSector,
        sectorsWithoutPrinter: const [],
      );
    }

    final tickets = <KitchenTicket>[];
    final sectorsWithoutPrinter = <String>[];
    for (final entry in itemsBySector.entries) {
      final sectorPrinters = printers
          .where(
            (printer) =>
                printer['is_active'] != false &&
                '${printer['sector'] ?? ''}' == entry.key,
          )
          .toList();
      if (sectorPrinters.isEmpty) {
        sectorsWithoutPrinter.add(entry.key);
        continue;
      }
      for (final printer in sectorPrinters) {
        tickets.add(
          KitchenTicket(
            printer: printer,
            text: _kitchenTicketText(
              order: order,
              table: table,
              command: command,
              items: entry.value,
              batchSerial: batchSerial,
              // O nome do setor vem da própria impressora: o cadastro já
              // devolve `sector_name`, então não precisa de outra consulta.
              sectorName: '${printer['sector_name'] ?? ''}',
              operatorName: operatorName,
              now: printedAt,
            ),
          ),
        );
      }
    }
    return KitchenTicketPlan(
      tickets: tickets,
      printersConsidered: printers.length,
      itemsBySector: sectorCounts,
      productsWithoutSector: productsWithoutSector,
      sectorsWithoutPrinter: sectorsWithoutPrinter,
    );
  }

  /// Rótulos do tipo de atendimento, iguais aos de `TIPO_ATENDIMENTO_COMANDA`
  /// no backend — as choices do modelo estão em inglês e não servem aqui.
  static const _kitchenOrderTypeLabels = <String, String>{
    'table': 'MESA',
    'command': 'COMANDA',
    'counter': 'BALCAO',
    'delivery': 'DELIVERY',
    'takeaway': 'RETIRADA',
  };

  static String _kitchenTicketText({
    required JsonMap? order,
    required JsonMap? table,
    required JsonMap? command,
    required List<JsonMap> items,
    required String batchSerial,
    required String sectorName,
    required String operatorName,
    required DateTime now,
  }) {
    const width = 32;
    String clip(String value) =>
        value.length > width ? value.substring(0, width) : value;
    const separator = '--------------------------------';

    final lines = <String>[clip(_center('NOVO PEDIDO', width))];
    if (sectorName.trim().isNotEmpty) {
      lines.add(clip(_center(sectorName.toUpperCase(), width)));
    }
    lines.add(separator);
    // Sem número de rodada aqui: quem numera a rodada é o backend, ao
    // processar a fila. Inventar um número localmente sairia errado no papel.
    final sequence = '${order?['sequence'] ?? ''}'.trim();
    if (sequence.isNotEmpty) lines.add(clip('PEDIDO #$sequence'));
    lines.add(_formatTicketTimestamp(now));
    lines.add(separator);

    final orderType = '${order?['order_type'] ?? ''}';
    if (orderType.isNotEmpty &&
        orderType != 'table' &&
        orderType != 'command') {
      lines.add(
        clip(_kitchenOrderTypeLabels[orderType] ?? orderType.toUpperCase()),
      );
    }
    if (table != null) lines.add(clip('MESA: ${table['number']}'));
    if (command != null) lines.add(clip('COMANDA: ${command['code']}'));
    final customer = '${order?['customer_name'] ?? ''}'.trim();
    if (customer.isNotEmpty) lines.add(clip('CLIENTE: $customer'));
    if (operatorName.trim().isNotEmpty) {
      lines.add(clip('ATENDENTE: ${operatorName.trim()}'));
    }
    lines.add(separator);

    var totalItems = 0.0;
    for (final item in items) {
      totalItems += ValueFormatters.number(item['quantity']);
      final quantity = _formatQuantity(item['quantity']);
      lines.add(
        clip('${quantity}x ${item['product_name']}${variationSuffix(item)}'),
      );
      for (final addon in (item['addons'] as List? ?? const [])) {
        if (addon is! Map) continue;
        lines.add(clip('  ${addon['addon_name']}'));
      }
      final note = '${item['customer_note'] ?? ''}';
      if (note.isNotEmpty) lines.add(clip('  OBS: $note'));
      lines.add(separator);
    }
    lines.add(
      _twoColumns('TOTAL DE ITENS', _formatQuantity(totalItems), width),
    );
    lines.addAll(['REF: $batchSerial', '']);
    return lines.join('\n');
  }

  /// Sufixo ` - Variação A, Variação B` para colar no nome do produto.
  ///
  /// Espelha `_variacoes_sufixo` em `backend/apps/printers/services.py`: a
  /// variação diz QUAL produto é (sabor, tamanho, ponto), então sai na mesma
  /// linha dele — quem vai para uma linha própria abaixo é o adicional.
  static String variationSuffix(JsonMap item) {
    final names = <String>[];
    for (final variation in (item['variations'] as List? ?? const [])) {
      final name = variation is Map ? variation['name'] : variation;
      final text = '${name ?? ''}'.trim();
      if (text.isNotEmpty) names.add(text);
    }
    return names.isEmpty ? '' : ' - ${names.join(', ')}';
  }

  static String _twoColumns(String left, String right, int width) {
    final gap = width - left.length - right.length;
    return gap < 1 ? '$left $right' : '$left${' ' * gap}$right';
  }

  static String _formatTicketTimestamp(DateTime value) {
    String two(int number) => number.toString().padLeft(2, '0');
    return '${two(value.day)}/${two(value.month)}/${value.year} '
        '${two(value.hour)}:${two(value.minute)}:${two(value.second)}';
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
    // Item cancelado continua na lista (a tela mostra o histórico e o servidor
    // precisa saber do cancelamento), mas não entra na conta. A tela já
    // passava só os ativos; o repositório passa a lista inteira, e sem este
    // filtro o total ficava com o valor do item que o cliente desistiu.
    final subtotal = items
        .where((item) => item['status'] != 'voided')
        .fold<double>(
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
