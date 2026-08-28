import '../../../core/data/entity_catalog.dart';
import '../../../core/data/offline_first_gateway.dart';
import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/mutation_relay.dart';
import '../../devices/domain/local_print_renderer.dart';
import '../../devices/services/local_device_agent.dart';
import '../../orders/presentation/order_presenter.dart';

/// Imprime no Caixa Principal em nome de quem chegou pelo relay sem
/// impressora própria — hoje, o app do garçom.
///
/// O app manda o pedido para o Principal e não imprime nada por conta
/// própria: quem tem a impressora física é este terminal. Um Caixa
/// Secundário já resolve isso sozinho, pela mesma trava que existe em
/// `home_page.dart` — ele só entrega aqui como "pendente" quando não
/// conseguiu falar com o Principal a tempo, e nesse caso já imprimiu e
/// marcou `offline_printed` antes de tentar de novo. Este responsável só
/// entra em ação quando essa marca não veio: foi o app do garçom que
/// mandou, ou o Caixa Secundário achou (errado, porque o Principal estava
/// sem internet) que a entrega já bastava.
///
/// Mesma trava de sempre: reivindica com `offline_printed` ANTES de mandar
/// papel, e devolve a marca se nada saiu. É o que impede a comanda de sair
/// duas vezes se a operação subir para o backend bem no instante em que este
/// terminal está decidindo imprimir.
class RelayPrintFallback {
  RelayPrintFallback({required this.api, required this.deviceAgent});

  final ApiClient api;
  final LocalDeviceAgent deviceAgent;

  Duration get _window => api.syncStatus.hasConnection
      ? const Duration(seconds: 3)
      : const Duration(milliseconds: 400);

  /// Lê o pedido ANTES da mutação ser aplicada — depois dela os itens já
  /// estão marcados como enviados/cancelados, e não haveria mais como saber
  /// o que mudou nesta chamada.
  Future<Map<String, dynamic>?> captureBeforeState(
    RelayMutation mutation,
  ) async {
    final route = EntityCatalog.resolve(mutation.path);
    if (route == null ||
        route.type != EntityCatalog.order ||
        route.entityId == null) {
      return null;
    }
    final action = route.action ?? '';
    final isRelevant =
        action == 'send-to-kitchen' ||
        (action.startsWith('items/') && action.endsWith('/void'));
    if (!isRelevant) return null;
    final gateway = api.localStore;
    if (gateway == null) return null;
    return (await gateway.orders.read(route.entityId!))?.payload;
  }

  Future<void> afterAcceptedMutation({
    required RelayMutation mutation,
    required Map<String, dynamic>? beforeOrder,
    required Map<String, dynamic> response,
  }) async {
    // Quem mandou já cuidou da impressão (Caixa Secundário que não alcançou
    // o Principal a tempo). Imprimir de novo aqui dobraria o cupom.
    if (mutation.body?['offline_printed'] == true) return;
    final operationId = '${response['_sync_operation_id'] ?? ''}';
    if (operationId.isEmpty || beforeOrder == null) return;

    final route = EntityCatalog.resolve(mutation.path);
    if (route == null || route.entityId == null) return;
    final action = route.action ?? '';
    try {
      if (action == 'send-to-kitchen') {
        await _handleSendToKitchen(
          orderId: route.entityId!,
          mutation: mutation,
          operationId: operationId,
          beforeOrder: beforeOrder,
        );
      } else if (action.startsWith('items/') && action.endsWith('/void')) {
        await _handleVoidItem(
          orderId: route.entityId!,
          itemId: action.split('/')[1],
          mutation: mutation,
          operationId: operationId,
          beforeOrder: beforeOrder,
        );
      }
    } catch (error) {
      // Uma falha aqui não pode derrubar a resposta do relay: o aparelho que
      // mandou o pedido já recebeu a confirmação de que ele foi salvo.
      AppLogger.instance.warning(
        'relay_impressao_por_conta_do_principal_falhou',
        data: {'path': mutation.path, 'causa': '$error'},
      );
    }
  }

  Future<void> _handleSendToKitchen({
    required String orderId,
    required RelayMutation mutation,
    required String operationId,
    required Map<String, dynamic> beforeOrder,
  }) async {
    final pendingItems = (beforeOrder['items'] as List? ?? const [])
        .whereType<Map>()
        .where((item) => item['status'] == 'pending')
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    if (pendingItems.isEmpty) return;
    if (await api.awaitDelivery(operationId, timeout: _window)) return;
    if (!await api.patchQueuedBody(operationId, {'offline_printed': true})) {
      return;
    }

    final gateway = api.localStore;
    if (gateway == null) return;
    final order = (await gateway.orders.read(orderId))?.payload ?? beforeOrder;
    final requestedSerial = '${mutation.body?['client_batch_serial'] ?? ''}';
    final batchSerial = requestedSerial.isNotEmpty
        ? requestedSerial
        : OrderPresenter.generateBatchSerial();

    final plan = OrderPresenter.buildOfflineKitchenTickets(
      order: order,
      table: await _relatedRecord(gateway, EntityCatalog.table, order['table']),
      command: await _relatedRecord(
        gateway,
        EntityCatalog.command,
        order['command'],
      ),
      pendingItems: pendingItems,
      products: await _allProducts(gateway),
      printers: await deviceAgent.ensurePrinters(),
      batchSerial: batchSerial,
      // Quem atendeu, não quem imprimiu: a comanda sai deste terminal, mas o
      // pedido é do garçom. Sem isto a cozinha lia `ATENDENTE: <caixa>` em
      // todo pedido que chegou pelo aplicativo.
      operatorName: await _operatorName(gateway, order),
    );
    // Quem mandou a operação pode não ter tela nenhuma (o app do garçom): se
    // o roteamento por setor não achar impressora, este registro é o único
    // lugar onde isso aparece.
    AppLogger.instance.info(
      'comanda_roteamento_relay',
      data: {'pedido': orderId, ...plan.toLog()},
    );

    var printed = false;
    for (final ticket in plan.tickets) {
      try {
        final printer = KitchenPrinter(
          PrinterDevice.fromJson(ticket.printer),
          runtime: deviceAgent.printing,
        );
        if ((await deviceAgent.submit(
          printer,
          printer.compose(content: ticket.text),
        )).accepted) {
          printed = true;
        }
      } catch (_) {
        // Outra impressora do setor ainda pode aceitar.
      }
    }
    if (!printed) {
      await api.patchQueuedBody(operationId, {'offline_printed': false});
    }
  }

  Future<void> _handleVoidItem({
    required String orderId,
    required String itemId,
    required RelayMutation mutation,
    required String operationId,
    required Map<String, dynamic> beforeOrder,
  }) async {
    final beforeItem = (beforeOrder['items'] as List? ?? const [])
        .whereType<Map>()
        .cast<Map<String, dynamic>>()
        .firstWhere((item) => '${item['id']}' == itemId, orElse: () => const {});
    // Item que ainda não tinha ido para a cozinha: nada a avisar lá.
    if (beforeItem.isEmpty || beforeItem['status'] == 'pending') return;
    if (await api.awaitDelivery(operationId, timeout: _window)) return;
    if (!await api.patchQueuedBody(operationId, {'offline_printed': true})) {
      return;
    }

    final gateway = api.localStore;
    if (gateway == null) return;
    final order = (await gateway.orders.read(orderId))?.payload ?? beforeOrder;
    final products = await _allProducts(gateway);
    final product = products.cast<Map<String, dynamic>?>().firstWhere(
      (candidate) => '${candidate?['id']}' == '${beforeItem['product']}',
      orElse: () => null,
    );
    final sector = '${product?['sector'] ?? ''}';
    if (sector.isEmpty) return;

    final text = LocalPrintRenderer.cancellationTicket(
      order: order,
      item: beforeItem,
      reason: '${mutation.body?['reason'] ?? ''}',
      table: await _relatedRecord(gateway, EntityCatalog.table, order['table']),
      command: await _relatedRecord(
        gateway,
        EntityCatalog.command,
        order['command'],
      ),
    );

    var printed = false;
    for (final printer in await deviceAgent.ensurePrinters()) {
      if ('${printer['sector'] ?? ''}' != sector) continue;
      try {
        final cancelPrinter = KitchenCancelPrinter(
          PrinterDevice.fromJson(printer),
          runtime: deviceAgent.printing,
        );
        if ((await deviceAgent.submit(
          cancelPrinter,
          cancelPrinter.compose(content: text),
        )).accepted) {
          printed = true;
        }
      } catch (_) {
        // Outra impressora do setor ainda pode aceitar.
      }
    }
    if (!printed) {
      await api.patchQueuedBody(operationId, {'offline_printed': false});
    }
  }

  /// Nome de quem abriu o pedido, pela cópia local de usuários.
  ///
  /// Vazio quando o terminal não conhece o usuário: a linha do atendente
  /// simplesmente não sai, o que é melhor do que sair com o nome errado.
  Future<String> _operatorName(
    OfflineFirstGateway gateway,
    Map<String, dynamic> order,
  ) async {
    final userId = '${order['responsible_user'] ?? ''}'.trim();
    if (userId.isEmpty) return '';
    final record = await gateway.repository(EntityCatalog.user).read(userId);
    final payload = record?.payload;
    if (payload == null) return '';
    final full = [
      '${payload['first_name'] ?? ''}'.trim(),
      '${payload['last_name'] ?? ''}'.trim(),
    ].where((part) => part.isNotEmpty).join(' ');
    return full.isNotEmpty ? full : '${payload['username'] ?? ''}'.trim();
  }

  Future<Map<String, dynamic>?> _relatedRecord(
    OfflineFirstGateway gateway,
    String type,
    Object? id,
  ) async {
    final key = '${id ?? ''}';
    if (key.isEmpty) return null;
    final record = await gateway.repository(type).read(key);
    return record?.payload;
  }

  Future<List<Map<String, dynamic>>> _allProducts(
    OfflineFirstGateway gateway,
  ) async {
    final page = await gateway
        .repository(EntityCatalog.product)
        .list(query: const {'page_size': 1000});
    return page.results;
  }
}
