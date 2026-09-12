import 'package:sqlite_async/sqlite_async.dart';

import 'order_item_status.dart';
import '../../features/orders/presentation/order_presenter.dart';
import '../formatters/decimal_money.dart';
import '../formatters/input_values.dart';
import '../formatters/value_formatters.dart';
import '../network/api_exception.dart';
import 'conflict_resolver.dart';
import 'entity_catalog.dart';
import 'entity_record.dart';
import 'entity_repository.dart';
import 'local_id.dart';
import 'sync_operation.dart';

/// Repositório do pedido — a entidade mais movimentada do PDV.
///
/// Além do CRUD genérico herdado de [EntityRepository], aplica localmente as
/// ações do atendimento (§30): abrir, lançar item, cancelar item, fechar,
/// mandar para a cozinha e receber. Cada ação grava o pedido resultante e a
/// operação de sincronização na mesma transação, e devolve na hora — nenhuma
/// delas espera a API.
///
/// O cálculo de totais, o preenchimento de um pedido offline e o preço
/// esperado de um item já existiam em [OrderPresenter], usados pelas telas.
/// São reaproveitados aqui em vez de reescritos: a conta que aparece na tela e
/// a que vai para o disco precisam ser a mesma (§28).
class OrderRepository extends EntityRepository {
  OrderRepository({
    required super.database,
    required super.scope,
    required this.products,
    super.cipher,
  }) : super(descriptor: _descriptor);

  static final EntityDescriptor _descriptor = EntityCatalog.byType(
    EntityCatalog.order,
  )!;

  /// Catálogo local, usado para resolver nome e preço do item sem rede.
  final EntityRepository products;

  /// Ponto único onde um rascunho vira pedido de verdade.
  ///
  /// Toda mutação de pedido passa por aqui, e toda mutação parte do payload
  /// guardado — então a marca de rascunho chega junto. Se a operação não for a
  /// promoção atômica do primeiro item, a criação é enfileirada ANTES dela.
  /// Concentrar a regra neste lugar evita ter de lembrar dela em cada método
  /// novo (fechar, pagar, mandar para a cozinha, pesar…).
  @override
  Future<EntityWrite> saveLocal(
    Map<String, dynamic> payload, {
    required SyncOperation operation,
    required String method,
    required String path,
    Map<String, dynamic>? query,
    String? id,
    Map<String, dynamic>? requestBody,
    Future<void> Function(SqliteWriteContext tx)? guard,
  }) async {
    var body = payload;
    if (isDraft(body) && path != _createWithItemPath) {
      body = await _materializeDraft(body, id ?? '${body['id'] ?? ''}');
    }
    return super.saveLocal(
      body,
      operation: operation,
      method: method,
      path: path,
      query: query,
      id: id,
      requestBody: requestBody,
      guard: guard,
    );
  }

  static const _createWithItemPath = '/orders/create-with-item/';

  // ------------------------------------------------------------- abertura

  /// Cria o pedido localmente com um identificador temporário (§7).
  Future<Map<String, dynamic>> createOrder({
    required String path,
    required Map<String, dynamic> body,
    required String? restaurantId,
    Map<String, dynamic>? table,
    Map<String, dynamic>? command,
  }) async {
    final orderId = LocalId.temporary();
    final type =
        '${body['order_type'] ?? (command != null ? 'command' : 'counter')}';
    final draft = OrderPresenter.completeOfflineOrder(
      {'id': orderId, '_offline_pending': true, ...body},
      restaurantId: restaurantId,
      type: type,
      table: table,
      command: command,
    );

    final now = DateTime.now().toUtc().toIso8601String();
    var payload = <String, dynamic>{
      ...draft,
      'id': orderId,
      'created_at': now,
      'updated_at': now,
    };

    // `/orders/create-with-item/` é o caminho do app do garçom: o pedido e o
    // primeiro item nascem juntos. Criar só o pedido deixaria o garçom olhando
    // uma comanda vazia logo depois de escolher o produto.
    final firstItem = body['item'];
    if (firstItem is Map) {
      payload = await _withNewItem(
        payload,
        Map<String, dynamic>.from(firstItem),
      );
      final record = await saveLocal(
        payload,
        operation: SyncOperation.create,
        method: 'POST',
        path: path,
        // O corpo enviado ao servidor carrega o UUID local: é ele que o backend
        // usa como chave de idempotência do pedido.
        requestBody: {...body, 'client_order_id': orderId},
        id: orderId,
      );
      return record.toApiJson();
    }

    // SEM item, o pedido ainda NÃO existe para o servidor.
    //
    // Escolher a comanda e a mesa é o operador montando a venda, não a venda
    // acontecendo. Enfileirar a criação aqui enchia o banco de pedidos vazios
    // — bastava entrar numa comanda, olhar e sair — e obrigava a inventar um
    // cancelamento para desfazer algo que nunca deveria ter nascido.
    //
    // O rascunho fica só neste terminal (`saveLocalEffect` não gera operação
    // de saída) e a tela trabalha com ele exatamente como trabalhava com o
    // pedido criado: mesmo id, mesmos campos. Quem o promove é o primeiro
    // item, em [addItem], por `/orders/create-with-item/` — pedido e item
    // nascem juntos, numa transação só.
    if (_promotableTypes.contains(type)) {
      final record = await saveLocalEffect({
        ...payload,
        draftMarker: true,
        // Como este pedido teria nascido, se o primeiro item não vier antes de
        // outra coisa. Ver [_materializeDraft].
        _draftPath: path,
        _draftBody: {...body, 'client_order_id': orderId},
      }, id: orderId);
      return record.toApiJson();
    }

    final record = await saveLocal(
      payload,
      operation: SyncOperation.create,
      method: 'POST',
      path: path,
      requestBody: {...body, 'client_order_id': orderId},
      id: orderId,
    );
    return record.toApiJson();
  }

  /// Marca de rascunho: o pedido existe só neste terminal.
  ///
  /// Sai do payload no instante em que o primeiro item o promove — e nunca é
  /// enviada ao servidor, que não conhece este conceito.
  ///
  /// SEM sublinhado na frente de propósito: `EntityRepository.sanitize` apaga
  /// toda chave assim antes de gravar, justamente para que marcas efêmeras não
  /// persistam. Esta precisa persistir — é ela que distingue, na próxima
  /// abertura da tela, um pedido que existe de um que ainda é intenção.
  static const draftMarker = 'local_draft';

  /// Tipos que `/orders/create-with-item/` sabe criar junto com o item.
  ///
  /// Um tipo fora desta lista (mesa, criada só por importação e base demo)
  /// segue o caminho antigo: não há endpoint atômico para ele, e adiar a
  /// criação deixaria o item sem pedido para entrar.
  static const _promotableTypes = {
    'command',
    'counter',
    'delivery',
    'takeaway',
  };

  static const _draftPath = 'local_draft_path';
  static const _draftBody = 'local_draft_body';

  /// O pedido ainda é um rascunho deste terminal?
  static bool isDraft(Map<String, dynamic> order) =>
      order[draftMarker] == true;

  static Map<String, dynamic> _withoutDraftMarks(Map<String, dynamic> order) =>
      Map<String, dynamic>.from(order)
        ..remove(draftMarker)
        ..remove(_draftPath)
        ..remove(_draftBody);

  /// Faz o rascunho existir para o servidor, do jeito antigo.
  ///
  /// O primeiro item promove o rascunho de um jeito melhor — pedido e item
  /// numa transação só ([addItem]). Mas QUALQUER outra operação sobre ele
  /// (mandar para a cozinha, fechar, receber) precisa de um pedido que o
  /// servidor conheça, senão ela subiria citando um identificador temporário
  /// que ninguém pode resolver. Nesse caso a criação vai primeiro, pelo mesmo
  /// caminho de sempre, e a operação segue atrás dela na fila.
  Future<Map<String, dynamic>> _materializeDraft(
    Map<String, dynamic> order,
    String orderId,
  ) async {
    final clean = _withoutDraftMarks(order);
    final body = order[_draftBody];
    await saveLocal(
      clean,
      operation: SyncOperation.create,
      method: 'POST',
      path: '${order[_draftPath] ?? '/orders/'}',
      requestBody: body is Map
          ? Map<String, dynamic>.from(body)
          : {'client_order_id': orderId},
      id: orderId,
    );
    return clean;
  }

  /// Monta o item a partir do catálogo local e devolve o pedido recalculado.
  Future<Map<String, dynamic>> _withNewItem(
    Map<String, dynamic> order,
    Map<String, dynamic> body, {
    String? itemId,
    Map<String, dynamic>? knownProduct,
  }) async {
    // `knownProduct` é o que a tela já tem na mão. Sem ele, um produto ausente
    // do catálogo local viraria um item sem nome e sem preço no pedido.
    // Produto ausente do catálogo local virava um item SEM NOME e SEM PREÇO no
    // pedido — de graça, e sem nada na tela dizendo o que aconteceu. O guard
    // `knownProduct` cobria só a tela; pelo relay (garçom, caixa secundário) o
    // item entrava assim. O backend recusa; aqui passa a recusar também.
    final productId = '${body['product'] ?? ''}'.trim();
    final product =
        knownProduct ?? (await products.read(productId))?.payload;
    if (product == null || product.isEmpty) {
      throw ApiException(
        productId.isEmpty
            ? 'Informe o produto do item.'
            : 'O produto do item não está no catálogo deste terminal.',
        statusCode: 400,
      );
    }
    // `quantity <= 0 ? 1 : quantity` era um silêncio caro: zero, negativo e
    // "duas" viravam UM item cobrado do cliente, e o backend recusava o mesmo
    // lançamento depois — a venda já impressa voltava `FAILED` na fila.
    final quantity = requireQuantity(
      body['quantity'] ?? body['weight_kg'],
      padrao: 1,
    );
    final item = OrderPresenter.offlineItem(
      response: {...body, 'id': itemId ?? LocalId.temporary()},
      product: product,
      quantity: quantity,
      customerNote: '${body['customer_note'] ?? ''}',
    );

    // O servidor agrupa itens PENDENTES iguais (mesmo produto, variações,
    // adicionais e observação). Aqui a tela mostrava duas linhas até a
    // sincronização acontecer — e então elas viravam uma, sozinhas. Com o
    // leitor isso deixa de ser detalhe: bipar cinco vezes o mesmo refrigerante
    // encheria a comanda de linhas de quantidade 1.
    final items = _itemsOf(order);
    final existingIndex = items.indexWhere(
      (candidate) => _groupsWith(candidate, item),
    );
    if (existingIndex < 0) {
      return OrderPresenter.withItems(order, [...items, item]);
    }
    final existing = items[existingIndex];
    final merged =
        ValueFormatters.number(existing['quantity']) +
        ValueFormatters.number(item['quantity']);
    final unitPrice = ValueFormatters.number(existing['unit_price']);
    items[existingIndex] = {
      ...existing,
      'quantity': merged,
      'total_price': DecimalMoney.asNumber(
        DecimalMoney.multiplyToMinorUnits(unitPrice, merged),
      ),
    };
    return OrderPresenter.withItems(order, items);
  }

  /// Dois itens são a MESMA linha do pedido?
  ///
  /// Só itens pendentes se juntam: um item já enviado à cozinha descreve o que
  /// a produção recebeu, e mexer na quantidade dele mudaria o passado. Produto
  /// vendido por peso também fica de fora — cada pesagem é uma leitura própria,
  /// e somá-las apagaria o registro de duas balanças diferentes.
  static bool _groupsWith(
    Map<String, dynamic> existing,
    Map<String, dynamic> item,
  ) {
    if ('${existing['status'] ?? ''}' != 'pending') return false;
    if ('${existing['product'] ?? ''}' != '${item['product'] ?? ''}') {
      return false;
    }
    if ('${existing['pricing_unit'] ?? 'unit'}' == 'kg') return false;
    if ('${existing['customer_note'] ?? ''}'.trim() !=
        '${item['customer_note'] ?? ''}'.trim()) {
      return false;
    }
    return _idsOf(existing['variations']) == _idsOf(item['variations']) &&
        _idsOf(existing['addons']) == _idsOf(item['addons']);
  }

  static String _idsOf(Object? value) {
    final ids =
        (value as List? ?? const [])
            .map(
              (entry) => entry is Map
                  ? '${entry['addon'] ?? entry['variation'] ?? entry['id'] ?? ''}'
                  : '$entry',
            )
            .where((id) => id.isNotEmpty)
            .toList()
          ..sort();
    return ids.join(',');
  }

  /// Fecha uma pesagem na comanda, sem servidor.
  ///
  /// Espelha `ScaleViewSet.checkout_command`: acha (ou abre) o pedido da
  /// comanda, lança o item pesado e os extras e recalcula — tudo em UMA
  /// operação de fila. Decompor em vários lançamentos duplicaria os itens
  /// quando a fila subisse, porque o servidor executa o `checkout-command`
  /// inteiro de novo.
  ///
  /// Sem `ScaleReading` (criá-la exige servidor), a operação enfileirada leva
  /// o **peso bruto**; o backend materializa a leitura no replay.
  Future<Map<String, dynamic>> checkoutCommand({
    required String scaleId,
    required Map<String, dynamic> command,
    required Map<String, dynamic> weighedProduct,
    required double weightKg,
    required List<Map<String, dynamic>> extras,
    required String? restaurantId,
    bool printedLocally = false,
  }) async {
    final existingId = '${command['current_order_id'] ?? ''}';
    final order = existingId.isEmpty ? null : await read(existingId);
    final orderId = order?.id ?? LocalId.temporary();

    var payload =
        order?.payload ??
        OrderPresenter.completeOfflineOrder(
          {'id': orderId, '_offline_pending': true},
          restaurantId: restaurantId,
          type: 'command',
          command: command,
        );
    payload = {
      ...payload,
      'id': orderId,
      'created_at':
          payload['created_at'] ?? DateTime.now().toUtc().toIso8601String(),
    };

    payload = await _withNewItem(payload, {
      'product': '${weighedProduct['id']}',
      'weight_kg': weightKg.toStringAsFixed(3),
    }, knownProduct: weighedProduct);
    for (final extra in extras) {
      payload = await _withNewItem(payload, extra);
    }

    final record = await saveLocal(
      payload,
      operation: order == null ? SyncOperation.create : SyncOperation.update,
      method: 'POST',
      path: '/scales/$scaleId/checkout-command/',
      requestBody: {
        'command_code': '${command['code'] ?? command['number'] ?? ''}',
        'weight_kg': weightKg.toStringAsFixed(3),
        'extras': extras,
        'client_order_id': orderId,
        // O terminal já imprimiu a nota; sem isto o backend criaria um
        // `PrintJob` novo e a nota sairia uma segunda vez ao sincronizar.
        'offline_printed': printedLocally,
      },
      id: orderId,
    );
    return record.toApiJson();
  }

  /// Atualiza a mesa do RASCUNHO ligado a esta comanda.
  ///
  /// Só mexe em rascunho: um pedido que o servidor já conhece tem o vínculo
  /// resolvido lá, com as regras de lá (ocupação da mesa, histórico de
  /// movimentação). E usa [saveLocalEffect] de propósito — trocar de mesa
  /// antes do primeiro item não é motivo para o pedido passar a existir.
  Future<void> refreshDraftTable({
    required String commandId,
    required String? tableId,
  }) async {
    if (commandId.isEmpty) return;
    final page = await list(query: {'command': commandId, 'page_size': 50});
    for (final order in page.results) {
      if (!isDraft(order)) continue;
      await saveLocalEffect({
        ...order,
        'table': tableId,
        if (tableId == null) 'table_number': null,
      }, id: '${order['id'] ?? ''}');
    }
  }

  // ------------------------------------------------------------------ itens

  /// Lança um item no pedido e recalcula os totais.
  Future<Map<String, dynamic>> addItem(
    String orderId, {
    required Map<String, dynamic> body,
  }) async {
    final order = await read(orderId);
    if (order == null) {
      throw StateError('Pedido $orderId não existe no armazenamento local.');
    }
    final itemId = LocalId.temporary();
    final updated = await _withNewItem(order.payload, body, itemId: itemId);
    // Com agrupamento, o item afetado pode ser um que já existia — devolver o
    // último da lista mostraria a linha errada na tela.
    final item = _itemsOf(updated).firstWhere(
      (candidate) => '${candidate['id']}' == itemId,
      orElse: () => _itemsOf(updated).last,
    );
    // PRIMEIRO ITEM DE UM RASCUNHO: é ele que faz o pedido existir.
    //
    // Em vez de duas operações na fila (criar o pedido, depois lançar o item),
    // sobe UMA — `/orders/create-with-item/`, que o backend já executa numa
    // transação só. É o mesmo caminho do app do garçom, e ele também resolve o
    // caso de a comanda já ter sido aberta por outro terminal enquanto isto
    // esperava na fila: lá o item entra no pedido que existe, em vez de
    // recusar.
    if (isDraft(order.payload)) {
      final promoted = Map<String, dynamic>.from(updated)
        ..remove(draftMarker);
      final record = await saveLocal(
        promoted,
        operation: SyncOperation.create,
        method: 'POST',
        path: _createWithItemPath,
        requestBody: {
          'order_type': '${promoted['order_type'] ?? 'counter'}',
          if (promoted['command'] != null) 'command': promoted['command'],
          if (promoted['table'] != null) 'table': promoted['table'],
          'client_order_id': orderId,
          'item': {...body, 'client_item_id': itemId},
        },
        id: orderId,
      );
      return {...record.toApiJson(), '_created_item': item};
    }

    final record = await saveLocal(
      updated,
      operation: SyncOperation.update,
      method: 'POST',
      path: '/orders/$orderId/items/',
      requestBody: {...body, 'client_item_id': itemId},
      id: orderId,
    );
    // A tela precisa do item recém-criado (para desenhar a linha) e do
    // pedido recalculado (para o total). Devolver os dois evita uma segunda
    // leitura logo em seguida.
    return {...record.toApiJson(), '_created_item': item};
  }

  /// Ajusta a quantidade de um item PENDENTE, do mesmo jeito que o servidor.
  ///
  /// Só item pendente: um já despachado descreve o que a cozinha recebeu, e
  /// mudar a quantidade dele reescreveria o passado sem ninguém na produção
  /// ficar sabendo. Por peso também não — a quantidade vem da balança.
  Future<Map<String, dynamic>> setItemQuantity(
    String orderId, {
    required String itemId,
    required double quantity,
  }) async {
    final order = await read(orderId);
    if (order == null) {
      throw StateError('Pedido $orderId não existe no armazenamento local.');
    }
    if (quantity <= 0) {
      throw ArgumentError(
        'Para remover o item, cancele-o informando o motivo.',
      );
    }
    final items = _itemsOf(order.payload);
    final index = items.indexWhere((item) => '${item['id']}' == itemId);
    if (index < 0) {
      throw StateError('Item $itemId não existe neste pedido.');
    }
    final item = items[index];
    if ('${item['status'] ?? ''}' != 'pending') {
      throw ArgumentError(
        'Só um item que ainda não foi para a produção pode ter a quantidade '
        'alterada.',
      );
    }
    if ('${item['pricing_unit'] ?? 'unit'}' == 'kg') {
      throw ArgumentError(
        'Produto vendido por peso: a quantidade vem da balança, não do teclado.',
      );
    }
    final unitPrice = ValueFormatters.number(item['unit_price']);
    items[index] = {
      ...item,
      'quantity': quantity,
      'total_price': DecimalMoney.asNumber(
        DecimalMoney.multiplyToMinorUnits(unitPrice, quantity),
      ),
      'addons': (item['addons'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (addon) => {
              ...Map<String, dynamic>.from(addon),
              'total_price': DecimalMoney.asNumber(
                DecimalMoney.multiplyToMinorUnits(
                  addon['unit_price'],
                  quantity,
                ),
              ),
            },
          )
          .toList(),
    };
    final record = await saveLocal(
      OrderPresenter.withItems(order.payload, items),
      operation: SyncOperation.update,
      method: 'POST',
      path: '/orders/$orderId/items/$itemId/quantity/',
      requestBody: {'quantity': quantity},
      id: orderId,
    );
    return record.toApiJson();
  }

  /// Cancela um item, do mesmo jeito que o servidor faria.
  Future<Map<String, dynamic>> voidItem(
    String orderId, {
    required String itemId,
    required Map<String, dynamic> body,
  }) async {
    final order = await read(orderId);
    if (order == null) {
      throw StateError('Pedido $orderId não existe no armazenamento local.');
    }
    final items = _itemsOf(order.payload)
        .map(
          (item) => '${item['id']}' == itemId
              ? {
                  ...item,
                  // O MESMO nome que o servidor vai gravar. Enquanto o
                  // cancelamento offline inventava um status só dele, o item
                  // trocava de nome ao sincronizar — e quem filtrasse por um
                  // dos dois nomes errava metade das vezes.
                  'status': OrderItemStatus.cancelled,
                  'void_reason': body['reason'],
                }
              : item,
        )
        .toList();
    final record = await saveLocal(
      OrderPresenter.withItems(order.payload, items),
      operation: SyncOperation.update,
      method: 'DELETE',
      path: '/orders/$orderId/items/$itemId/void/',
      requestBody: body,
      id: orderId,
    );
    return record.toApiJson();
  }

  // ------------------------------------------------------- estado do pedido

  /// Marca a rodada como enviada à produção.
  ///
  /// A impressão em si continua sendo responsabilidade do terminal (§17) e
  /// não é tocada aqui: este método só registra o estado do pedido.
  Future<Map<String, dynamic>> sendToKitchen(
    String orderId, {
    required Map<String, dynamic> body,
  }) async {
    final order = await read(orderId);
    if (order == null) {
      throw StateError('Pedido $orderId não existe no armazenamento local.');
    }
    final record = await saveLocal(
      OrderPresenter.sentToKitchen(order.payload),
      operation: SyncOperation.update,
      method: 'POST',
      path: '/orders/$orderId/send-to-kitchen/',
      requestBody: body,
      id: orderId,
    );
    return record.toApiJson();
  }

  /// Fecha o pedido: aplica taxa de serviço e desconto e trava novos itens.
  Future<Map<String, dynamic>> close(
    String orderId, {
    required Map<String, dynamic> body,
    required double serviceFeePercent,
  }) async {
    final order = await read(orderId);
    if (order == null) {
      throw StateError('Pedido $orderId não existe no armazenamento local.');
    }
    // Desconto vinha direto do corpo para o cálculo: texto virava zero em
    // silêncio, negativo AUMENTAVA o total e um valor maior que a mercadoria
    // zerava a venda. O backend recusa os três — sem a mesma regra aqui, a
    // venda era impressa e cobrada antes de a fila descobrir.
    final subtotal = ValueFormatters.number(order.payload['subtotal']);
    final discount = requireMoney(
      body['discount'] ?? order.payload['discount'],
      field: 'discount',
      label: 'o desconto',
      padrao: 0,
    );
    if (discount > subtotal) {
      throw const ApiException(
        'O desconto não pode ser maior que o subtotal do pedido.',
        statusCode: 400,
      );
    }
    final closed = OrderPresenter.closeOfflineOrder(
      {
        ...order.payload,
        'discount': discount,
        'fiscal_customer_cpf':
            body['fiscal_customer_cpf'] ??
            order.payload['fiscal_customer_cpf'] ??
            '',
      },
      serviceFeeEnabled: body['service_fee_enabled'] != false,
      serviceFeePercent: serviceFeePercent,
    );
    final record = await saveLocal(
      closed,
      operation: SyncOperation.update,
      method: 'POST',
      path: '/orders/$orderId/close/',
      requestBody: {...body, 'expected_total': closed['total']},
      id: orderId,
    );
    return record.toApiJson();
  }

  /// Registra um recebimento e atualiza a situação de pagamento.
  ///
  /// O pagamento nasce com UUID próprio (§7): o mesmo identificador vai no
  /// corpo enviado ao servidor, então um reenvio por timeout não cobra duas
  /// vezes.
  Future<Map<String, dynamic>> pay(
    String orderId, {
    required Map<String, dynamic> body,
    Map<String, dynamic>? method,
  }) async {
    final order = await read(orderId);
    if (order == null) {
      throw StateError('Pedido $orderId não existe no armazenamento local.');
    }
    final paymentId = LocalId.temporary();
    final total = ValueFormatters.number(order.payload['total']);
    final payments = _paymentsOf(order.payload);
    // Recebimento sem valor registrava R$ 0,00 como pagamento válido e dava a
    // venda por quitada; com texto no campo, o mesmo.
    final amount = requireMoney(body['amount'], field: 'amount', label: 'o valor recebido');
    // Conta os recebimentos JÁ CONFIRMADOS pelo servidor junto com os que
    // ainda estão na fila. Olhando só a fila, uma venda paga metade online e
    // metade offline calculava o troco sobre o valor cheio e devolvia dinheiro
    // a mais ao cliente.
    final alreadyPaid = [..._serverPaymentsOf(order.payload), ...payments]
        .fold<double>(
          0,
          (sum, payment) => sum + ValueFormatters.number(payment['amount']),
        );
    final remainingBefore = (total - alreadyPaid).clamp(0, double.infinity);
    // O troco não depende mais da forma de pagamento: qualquer uma pode
    // receber acima do restante e devolver a diferença (a maquininha cobrou um
    // valor redondo, o cliente pediu parte em espécie de volta). Só o que
    // ENTRA na gaveta continua sendo o dinheiro — quem decide isso é
    // `_mirrorCashSale`, no gateway.
    final metadata = body['metadata'];
    final cardSubtype = metadata is Map
        ? '${metadata['card_subtype'] ?? ''}'
        : '';
    final change = (amount - remainingBefore)
        .clamp(0, double.infinity)
        .toDouble();
    final applied = amount - change;

    final payment = {
      'id': paymentId,
      'order': orderId,
      'payment_method': body['payment_method'],
      'payment_method_name': method?['name'],
      'method_type': method?['method_type'],
      'card_subtype': cardSubtype,
      'amount': applied.toStringAsFixed(2),
      'received_amount': amount.toStringAsFixed(2),
      'change_amount': change.toStringAsFixed(2),
      'created_at': DateTime.now().toUtc().toIso8601String(),
      '_offline_pending': true,
    };
    final updatedPayments = [...payments, payment];
    final paid = alreadyPaid + applied >= total - 0.009;
    final record = await saveLocal(
      {
        ...order.payload,
        'offline_payments': updatedPayments,
        'payment_status': paid ? 'paid' : 'partial',
        'status': paid ? 'paid' : 'awaiting_payment',
      },
      operation: SyncOperation.update,
      method: 'POST',
      path: '/orders/$orderId/pay/',
      requestBody: {...body, 'client_payment_id': paymentId},
      id: orderId,
    );
    return {...record.toApiJson(), '_created_payment': payment};
  }

  /// Remove um recebimento que ainda não subiu para o servidor.
  ///
  /// Um pagamento lançado aqui só existe neste terminal até a fila entregá-lo.
  /// A tela mandava `DELETE /orders/<id>/payments/offline-…/` mesmo assim, e o
  /// servidor respondia "não é um UUID válido" — o operador ficava sem
  /// conseguir corrigir a forma de pagamento que acabara de escolher.
  ///
  /// Desfazer aqui é a operação inteira: a linha sai do pedido, os totais
  /// voltam ao que eram e a operação `pay` correspondente sai da fila (quem
  /// remove é o chamador, que sabe o escopo). Sem tirá-la da fila, o servidor
  /// registraria depois um dinheiro que o operador já apagou.
  Future<Map<String, dynamic>> removePendingPayment(
    String orderId, {
    required String paymentId,
  }) async {
    final order = await read(orderId);
    if (order == null) {
      throw StateError('Pedido $orderId não existe no armazenamento local.');
    }
    final remaining = _paymentsOf(
      order.payload,
    ).where((payment) => '${payment['id']}' != paymentId).toList();

    final total = ValueFormatters.number(order.payload['total']);
    final paid = [..._serverPaymentsOf(order.payload), ...remaining]
        .fold<double>(
          0,
          (sum, payment) => sum + ValueFormatters.number(payment['amount']),
        );
    final record = await saveLocalEffect({
      ...order.payload,
      'offline_payments': remaining,
      'payment_status': paid <= 0
          ? 'pending'
          : (paid >= total - 0.009 ? 'paid' : 'partial'),
      // Um pedido que deixou de estar quitado volta a aguardar pagamento —
      // é o mesmo estado que `cancel_payment` grava no servidor.
      'status': paid >= total - 0.009 ? 'paid' : 'awaiting_payment',
    }, id: orderId);
    return record.toApiJson();
  }

  /// Remove apenas os recebimentos locais de tentativas recusadas.
  ///
  /// Usado quando o operador entra novamente no pagamento: o servidor
  /// confirmou que aquelas requisições não foram aplicadas, portanto manter
  /// o efeito otimista faria a tela considerar a venda quitada para sempre.
  Future<void> removeRejectedPayments(
    String orderId,
    Set<String> paymentIds,
  ) async {
    if (paymentIds.isEmpty) return;
    final order = await read(orderId);
    if (order == null) return;
    final remaining = _paymentsOf(
      order.payload,
    ).where((payment) => !paymentIds.contains('${payment['id']}')).toList();
    final total = ValueFormatters.number(order.payload['total']);
    final paid = [..._serverPaymentsOf(order.payload), ...remaining]
        .fold<double>(
          0,
          (sum, payment) => sum + ValueFormatters.number(payment['amount']),
        );
    await saveLocalEffect({
      ...order.payload,
      'offline_payments': remaining,
      'payment_status': paid <= 0
          ? 'pending'
          : (paid >= total - 0.009 ? 'paid' : 'partial'),
      'status': paid >= total - 0.009 ? 'paid' : 'open',
    }, id: orderId);
  }

  /// Recebimentos conhecidos localmente, no formato de `/orders/<id>/payments/`.
  ///
  /// Junta o que o servidor confirmou com o que ainda está na fila, sem
  /// repetir: entre a confirmação da entrega e a próxima leitura do servidor,
  /// o mesmo recebimento existe nos dois lugares com o id definitivo.
  Future<List<Map<String, dynamic>>> payments(String orderId) async {
    final order = await read(orderId);
    if (order == null) return const [];
    final byId = <String, Map<String, dynamic>>{};
    for (final payment in [
      ..._serverPaymentsOf(order.payload),
      ..._paymentsOf(order.payload),
    ]) {
      byId['${payment['id']}'] = payment;
    }
    return byId.values.toList();
  }

  /// Apaga o pedido que só existe neste terminal.
  ///
  /// Diferente de `markRemoteDeleted`, que registra uma exclusão vinda do
  /// servidor: aqui o pedido nunca chegou lá, então não há exclusão a
  /// espelhar — a linha simplesmente deixa de existir, como se a comanda
  /// nunca tivesse sido aberta.
  Future<void> discardLocal(String orderId) async {
    if (!LocalId.isTemporary(orderId)) return;
    await database.execute(
      '''
      DELETE FROM entities
      WHERE scope = ? AND entity_type = ? AND entity_id = ?
      ''',
      [scope, type, orderId],
    );
  }

  /// Grava a versão do servidor preservando o que ainda não subiu.
  ///
  /// Itens e pagamentos criados offline (id `offline-...`) continuam na tela
  /// até a fila esvaziar; sem isso o operador via o lançamento sumir e achava
  /// que tinha se perdido.
  @override
  Future<EntityRecord?> applyRemote(
    Map<String, dynamic> payload, {
    bool overwriteLocalChanges = false,
    String? ignoreQueuedOperationId,
  }) async {
    final orderId = '${payload['id'] ?? ''}';
    if (orderId.isEmpty) return null;
    final stored = await read(orderId, includeDeleted: true);
    if (stored == null) {
      return super.applyRemote(
        payload,
        overwriteLocalChanges: overwriteLocalChanges,
        ignoreQueuedOperationId: ignoreQueuedOperationId,
      );
    }

    // Numa leitura comum, a decisão é do resolvedor: o que o operador acabou
    // de lançar e ainda não subiu vence a cópia do servidor. A regra mora lá,
    // não aqui — repeti-la é como as duas cópias acabam divergindo.
    if (!overwriteLocalChanges) {
      if (ConflictResolver.isStale(local: stored, remote: payload)) return null;
      if (ConflictResolver.resolve(
            local: stored,
            remote: payload,
            confirmedByDelivery: false,
          ) ==
          ConflictOutcome.keepLocal) {
        return null;
      }
    }

    // Mesmo confirmando a entrega, itens e recebimentos que AINDA não subiram
    // continuam na tela. A confirmação cobre uma operação só: quando a criação
    // do pedido sobe, os itens lançados depois dela ainda estão na fila, e
    // deixá-los cair faria o lançamento sumir da frente do operador.
    final pendingItems = _itemsOf(
      stored.payload,
    ).where((item) => LocalId.isTemporary('${item['id']}')).toList();
    final pendingPayments = _paymentsOf(
      stored.payload,
    ).where((item) => LocalId.isTemporary('${item['id']}')).toList();

    var merged = Map<String, dynamic>.from(payload);
    if (pendingItems.isNotEmpty) {
      final remoteIds = _itemsOf(
        payload,
      ).map((item) => '${item['id']}').toSet();
      merged = OrderPresenter.withItems(merged, [
        ..._itemsOf(payload),
        // Um item já reconciliado (id real) chega pelos dois lados; manter os
        // dois somaria o mesmo item duas vezes na conta.
        ...pendingItems.where((item) => !remoteIds.contains('${item['id']}')),
      ]);
    }
    if (pendingPayments.isNotEmpty) {
      merged['offline_payments'] = pendingPayments;
    }
    return super.applyRemote(
      merged,
      overwriteLocalChanges: true,
      ignoreQueuedOperationId: ignoreQueuedOperationId,
    );
  }

  static List<Map<String, dynamic>> _itemsOf(Map<String, dynamic> order) =>
      (order['items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();

  static List<Map<String, dynamic>> _serverPaymentsOf(
    Map<String, dynamic> order,
  ) => (order['payments'] as List? ?? const [])
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .toList();

  static List<Map<String, dynamic>> _paymentsOf(Map<String, dynamic> order) =>
      (order['offline_payments'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
}
