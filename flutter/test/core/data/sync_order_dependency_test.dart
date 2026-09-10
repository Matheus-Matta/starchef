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

  group('espera por um lançamento que não existe mais', () {
    // O caso real: sem rede, o operador cancelou um item e fechou o pedido.
    // O cancelamento citava o id temporário de um item cuja criação não está
    // mais na fila, então NADA no mundo pode traduzi-lo. `claimNext` pulava a
    // operação toda vez, para sempre: ela nunca era tentada, então nunca tinha
    // erro, nunca mudava de estado, e a tela de revisão — que só oferece
    // "tentar" e "descartar" para operações recusadas — não dava saída
    // nenhuma. O fechamento, barrado pelo antecessor, congelava junto, e o
    // operador ficava sem conseguir receber.

    test(
      'vira pendência visível em vez de esperar para sempre',
      () async {
        await enqueue(
          'pedido-1',
          '/orders/pedido-1/items/offline-item-orfao/void/',
        );
        await enqueue('pedido-1', '/orders/pedido-1/close/');

        await sync.syncNow();

        final entries = await stack.queue.entries(scope: TestPdvStack.scope);
        final encalhada = entries.first;
        expect(
          encalhada.status,
          SyncQueueStatus.failed,
          reason: 'sem isso ela fica PENDING e invisível para sempre',
        );
        expect(encalhada.lastError, contains('offline-item-orfao'));
        // Nenhuma tentativa saiu: o problema não é o servidor.
        expect(
          transport.requests.where((request) => request.method != 'GET'),
          isEmpty,
        );
      },
    );

    test('descartar a encalhada libera o fechamento preso atrás', () async {
      await enqueue(
        'pedido-1',
        '/orders/pedido-1/items/offline-item-orfao/void/',
      );
      await enqueue('pedido-1', '/orders/pedido-1/close/');
      await sync.syncNow();

      final encalhadas = await stack.queue.entries(
        scope: TestPdvStack.scope,
        onlyFailed: true,
      );
      expect(await stack.queue.discardFailed(encalhadas.single.id), isTrue);
      await sync.syncNow();

      expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
      expect(
        transport.requests.map((request) => request.path),
        contains('/orders/pedido-1/close/'),
      );
    });

    test(
      'esperar por uma criação que AINDA está na fila continua valendo',
      () async {
        // A distinção que importa: aqui a criação do item está logo acima na
        // fila. A espera é legítima e se resolve sozinha — derrubá-la seria
        // transformar o funcionamento normal em pendência manual.
        await stack.queue.enqueue(
          scope: TestPdvStack.scope,
          entityType: EntityCatalog.order,
          entityId: 'pedido-1',
          operation: SyncOperation.update,
          method: 'POST',
          path: '/orders/pedido-1/items/',
          payload: {'client_item_id': 'offline-item-1'},
        );
        await enqueue('pedido-1', '/orders/pedido-1/items/offline-item-1/void/');

        await stack.queue.failStrandedDependencies(scope: TestPdvStack.scope);

        final entries = await stack.queue.entries(scope: TestPdvStack.scope);
        expect(entries.every((e) => e.status == SyncQueueStatus.pending), isTrue);
      },
    );

    test(
      'uma criação RECUSADA ainda pode ressuscitar quem depende dela',
      () async {
        // A criação do item foi recusada, mas o operador pode reenviá-la pela
        // tela de revisão. Enquanto ela existir na fila, quem depende do id
        // dela continua esperando — não é uma espera impossível.
        await stack.queue.enqueue(
          scope: TestPdvStack.scope,
          entityType: EntityCatalog.order,
          entityId: 'pedido-1',
          operation: SyncOperation.update,
          method: 'POST',
          path: '/orders/pedido-1/items/',
          payload: {'client_item_id': 'offline-item-1'},
        );
        await enqueue('pedido-1', '/orders/pedido-1/items/offline-item-1/void/');
        final criacao = await stack.queue.claimNext(scope: TestPdvStack.scope);
        await stack.queue.markFailed(criacao!.id, error: 'Produto inativo.');

        await stack.queue.failStrandedDependencies(scope: TestPdvStack.scope);

        final entries = await stack.queue.entries(scope: TestPdvStack.scope);
        final void_ = entries.firstWhere((e) => e.path.endsWith('/void/'));
        expect(void_.status, SyncQueueStatus.pending);
      },
    );

    test(
      'descartar a criação recusada leva junto quem dependia dela',
      () async {
        // Fecha a porta pela qual o encalhe entra: sem isto, descartar a
        // criação do item deixava o cancelamento dele órfão na fila, citando
        // um id que ninguém mais pode resolver.
        await stack.queue.enqueue(
          scope: TestPdvStack.scope,
          entityType: EntityCatalog.order,
          entityId: 'pedido-1',
          operation: SyncOperation.update,
          method: 'POST',
          path: '/orders/pedido-1/items/',
          payload: {'client_item_id': 'offline-item-1'},
        );
        await enqueue('pedido-1', '/orders/pedido-1/items/offline-item-1/void/');
        await enqueue('pedido-1', '/orders/pedido-1/close/');
        final criacao = await stack.queue.claimNext(scope: TestPdvStack.scope);
        await stack.queue.markFailed(criacao!.id, error: 'Produto inativo.');

        expect(await stack.queue.discardFailed(criacao.id), isTrue);

        final restantes = await stack.queue.entries(scope: TestPdvStack.scope);
        expect(
          restantes.map((entry) => entry.path),
          ['/orders/pedido-1/close/'],
          reason: 'o cancelamento do item descartado não pode sobrar órfão',
        );
      },
    );
  });
}
