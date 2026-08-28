import '../../features/orders/presentation/order_presenter.dart';
import '../formatters/value_formatters.dart';
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

  static final EntityDescriptor _descriptor =
      EntityCatalog.byType(EntityCatalog.order)!;

  /// Catálogo local, usado para resolver nome e preço do item sem rede.
  final EntityRepository products;

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
    final type = '${body['order_type'] ?? (command != null ? 'command' : 'counter')}';
    final draft = OrderPresenter.completeOfflineOrder({
      'id': orderId,
      '_offline_pending': true,
      ...body,
    }, restaurantId: restaurantId, type: type, table: table, command: command);

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
    }

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

  /// Monta o item a partir do catálogo local e devolve o pedido recalculado.
  Future<Map<String, dynamic>> _withNewItem(
    Map<String, dynamic> order,
    Map<String, dynamic> body, {
    String? itemId,
    Map<String, dynamic>? knownProduct,
  }) async {
    // `knownProduct` é o que a tela já tem na mão. Sem ele, um produto ausente
    // do catálogo local viraria um item sem nome e sem preço no pedido.
    final product =
        knownProduct ??
        (await products.read('${body['product'] ?? ''}'))?.payload ??
        <String, dynamic>{};
    final quantity = ValueFormatters.number(
      body['quantity'] ?? body['weight_kg'] ?? 1,
    );
    final item = OrderPresenter.offlineItem(
      response: {...body, 'id': itemId ?? LocalId.temporary()},
      product: product,
      quantity: quantity <= 0 ? 1 : quantity,
      customerNote: '${body['customer_note'] ?? ''}',
    );
    return OrderPresenter.withItems(order, [..._itemsOf(order), item]);
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

    var payload = order?.payload ??
        OrderPresenter.completeOfflineOrder(
          {'id': orderId, '_offline_pending': true},
          restaurantId: restaurantId,
          type: 'command',
          command: command,
        );
    payload = {
      ...payload,
      'id': orderId,
      'created_at': payload['created_at'] ??
          DateTime.now().toUtc().toIso8601String(),
    };

    payload = await _withNewItem(
      payload,
      {
        'product': '${weighedProduct['id']}',
        'weight_kg': weightKg.toStringAsFixed(3),
      },
      knownProduct: weighedProduct,
    );
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
    final updated = await _withNewItem(
      order.payload,
      body,
      itemId: itemId,
    );
    final item = _itemsOf(updated).last;
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
                  'status': 'voided',
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
    final closed = OrderPresenter.closeOfflineOrder(
      {...order.payload, 'discount': body['discount'] ?? order.payload['discount']},
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
    final amount = ValueFormatters.number(body['amount']);
    // Conta os recebimentos JÁ CONFIRMADOS pelo servidor junto com os que
    // ainda estão na fila. Olhando só a fila, uma venda paga metade online e
    // metade offline calculava o troco sobre o valor cheio e devolvia dinheiro
    // a mais ao cliente.
    final alreadyPaid = [
      ..._serverPaymentsOf(order.payload),
      ...payments,
    ].fold<double>(
      0,
      (sum, payment) => sum + ValueFormatters.number(payment['amount']),
    );
    final remainingBefore = (total - alreadyPaid).clamp(0, double.infinity);
    final isCash = '${method?['method_type'] ?? ''}' == 'cash';
    final change = isCash
        ? (amount - remainingBefore).clamp(0, double.infinity).toDouble()
        : 0.0;
    final applied = amount - change;

    final payment = {
      'id': paymentId,
      'order': orderId,
      'payment_method': body['payment_method'],
      'payment_method_name': method?['name'],
      'method_type': method?['method_type'],
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
      final remoteIds = _itemsOf(payload).map((item) => '${item['id']}').toSet();
      merged = OrderPresenter.withItems(merged, [
        ..._itemsOf(payload),
        // Um item já reconciliado (id real) chega pelos dois lados; manter os
        // dois somaria o mesmo item duas vezes na conta.
        ...pendingItems.where(
          (item) => !remoteIds.contains('${item['id']}'),
        ),
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
  ) =>
      (order['payments'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();

  static List<Map<String, dynamic>> _paymentsOf(Map<String, dynamic> order) =>
      (order['offline_payments'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
}
