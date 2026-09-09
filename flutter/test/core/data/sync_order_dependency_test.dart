import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/sync_operation.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';

import 'pdv_test_support.dart';

void main() {
  late TestPdvStack stack;
  late FakeSyncTransport transport;
  late SyncService sync;

  setUp(() async {
    stack = await TestPdvStack.create();
    transport = FakeSyncTransport();
    sync = SyncService(gateway: stack.gateway, transport: transport);
  });

  tearDown(() async {
    await sync.dispose();
    await stack.dispose();
  });

  Future<void> enqueue(
    String entityId,
    String path, {
    Map<String, dynamic>? payload,
  }) => stack.queue.enqueue(
    scope: TestPdvStack.scope,
    entityType: EntityCatalog.order,
    entityId: entityId,
    operation: SyncOperation.update,
    method: 'POST',
    path: path,
    payload: payload,
  );

  test(
    'duas instâncias não enviam etapas do mesmo pedido em paralelo',
    () async {
      await enqueue('pedido-1', '/orders/pedido-1/items/');
      await enqueue('pedido-1', '/orders/pedido-1/close/');
      await enqueue('pedido-2', '/orders/pedido-2/items/');

      final item = await stack.queue.claimNext(scope: TestPdvStack.scope);
      final independente = await stack.queue.claimNext(
        scope: TestPdvStack.scope,
      );

      expect(item!.path, '/orders/pedido-1/items/');
      expect(independente!.path, '/orders/pedido-2/items/');
      expect(
        (await stack.queue.entries(
          scope: TestPdvStack.scope,
        )).firstWhere((entry) => entry.path.endsWith('/close/')).status.name,
        'pending',
      );
    },
  );

  test('recusa bloqueia somente as próximas etapas da mesma venda', () async {
    await enqueue('pedido-1', '/orders/pedido-1/close/');
    await enqueue('pedido-1', '/orders/pedido-1/pay/');
    await enqueue('pedido-2', '/orders/pedido-2/close/');

    final close = await stack.queue.claimNext(scope: TestPdvStack.scope);
    await stack.queue.markFailed(close!.id, error: 'Total divergente.');

    final outraVenda = await stack.queue.claimNext(scope: TestPdvStack.scope);
    expect(outraVenda!.entityId, 'pedido-2');
    await stack.queue.markSynced(outraVenda.id);
    expect(await stack.queue.claimNext(scope: TestPdvStack.scope), isNull);
    expect(
      (await stack.queue.failureForEntity(
        scope: TestPdvStack.scope,
        entityType: EntityCatalog.order,
        entityId: 'pedido-1',
      ))?.lastError,
      'Total divergente.',
    );
  });

  test('item corretivo passa pelo fechamento recusado', () async {
    await enqueue('pedido-1', '/orders/pedido-1/close/');
    await enqueue('pedido-1', '/orders/pedido-1/pay/');
    await enqueue('pedido-1', '/orders/pedido-1/items/');
    await enqueue('pedido-1', '/orders/pedido-1/send-to-kitchen/');

    final close = await stack.queue.claimNext(scope: TestPdvStack.scope);
    await stack.queue.markFailed(close!.id, error: 'Total divergente.');

    final item = await stack.queue.claimNext(scope: TestPdvStack.scope);
    expect(item!.path, '/orders/pedido-1/items/');
    await stack.queue.markSynced(item.id);
    final kitchen = await stack.queue.claimNext(scope: TestPdvStack.scope);
    expect(kitchen!.path, '/orders/pedido-1/send-to-kitchen/');
    await stack.queue.markSynced(kitchen.id);
    // O pagamento antigo continua dependente do fechamento recusado.
    expect(await stack.queue.claimNext(scope: TestPdvStack.scope), isNull);
  });

  test('item em backoff cede a vez ao próximo item', () async {
    await enqueue('pedido-1', '/orders/pedido-1/items/');
    await enqueue('pedido-1', '/orders/pedido-1/items/');

    final first = await stack.queue.claimNext(scope: TestPdvStack.scope);
    await stack.queue.markRetry(first!.id, attempts: 1, error: 'Timeout.');

    final second = await stack.queue.claimNext(scope: TestPdvStack.scope);
    expect(second, isNotNull);
    expect(second!.id, isNot(first.id));
  });

  test('falha temporária isolada não interrompe o ciclo inteiro', () async {
    await enqueue('pedido-1', '/orders/pedido-1/items/');
    await enqueue('pedido-2', '/orders/pedido-2/items/');
    transport.handlers['POST /orders/pedido-1/items/'] = (_) =>
        const TransientSyncFailure('Servidor ocupado.', offline: false);
    transport.handlers['POST /orders/pedido-2/items/'] = (_) => {
      'id': 'pedido-2',
      'items': const [],
    };

    await sync.push();

    expect(transport.requests.map((request) => request.path), [
      '/orders/pedido-1/items/',
      '/orders/pedido-2/items/',
    ]);
    final remaining = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(remaining.single.entityId, 'pedido-1');
    expect(remaining.single.nextRetryAt, isNotNull);
  });

  test('queda em um envio cede a vez às próximas operações', () async {
    await enqueue('pedido-1', '/orders/pedido-1/items/');
    await enqueue('pedido-2', '/orders/pedido-2/items/');
    transport.handlers['POST /orders/pedido-1/items/'] = (_) =>
        const TransientSyncFailure('Conexão caiu durante o envio.');
    transport.handlers['POST /orders/pedido-2/items/'] = (_) => {
      'id': 'pedido-2',
      'items': const [],
    };

    await sync.push();

    expect(transport.requests.map((request) => request.path), [
      '/orders/pedido-1/items/',
      '/orders/pedido-2/items/',
    ]);
    final remaining = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(remaining.single.entityId, 'pedido-1');
  });

  test('sessão inválida de uma origem não bloqueia as demais', () async {
    await enqueue('pedido-1', '/orders/pedido-1/items/');
    await enqueue('pedido-2', '/orders/pedido-2/items/');
    transport.handlers['POST /orders/pedido-1/items/'] = (_) =>
        const ApiException('Sessão expirada.', statusCode: 401);
    transport.handlers['POST /orders/pedido-2/items/'] = (_) => {
      'id': 'pedido-2',
      'items': const [],
    };

    await sync.push();

    expect(transport.requests.map((request) => request.path), [
      '/orders/pedido-1/items/',
      '/orders/pedido-2/items/',
    ]);
    final remaining = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(remaining.single.entityId, 'pedido-1');
    expect(remaining.single.nextRetryAt, isNotNull);
  });

  test('nova finalização substitui a recusada sem apagar itens', () async {
    await enqueue('pedido-1', '/orders/pedido-1/close/');
    await enqueue(
      'pedido-1',
      '/orders/pedido-1/pay/',
      payload: {'client_payment_id': 'offline-pagamento'},
    );
    await enqueue('pedido-1', '/orders/pedido-1/items/');
    final close = await stack.queue.claimNext(scope: TestPdvStack.scope);
    await stack.queue.markFailed(close!.id, error: 'Total divergente.');

    final removed = await stack.queue.supersedeRejectedOrderFinalization(
      scope: TestPdvStack.scope,
      orderId: 'pedido-1',
    );

    expect(removed, hasLength(2));
    expect(removed.last.payload?['client_payment_id'], 'offline-pagamento');
    final remaining = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(remaining.single.path, '/orders/pedido-1/items/');
  });
}
