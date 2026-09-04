import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/sync_operation.dart';
import 'package:starchef_pdv/core/data/sync_queue_service.dart';

import 'pdv_test_support.dart';

/// A fila é o que separa "a venda está salva" de "a venda chegou ao servidor".
/// Se ela errar a ordem, duplicar ou travar, a loja sente — por isso estes
/// testes cobrem FIFO (§6), dependência entre operações, idempotência (§7),
/// backoff (§23) e a diferença entre erro temporário e erro que exige análise.
void main() {
  late TestPdvStack stack;
  const scope = TestPdvStack.scope;

  setUp(() async => stack = await TestPdvStack.create());
  tearDown(() async => stack.dispose());

  Future<String> enqueue({
    required String path,
    String entityId = 'entidade-1',
    String method = 'POST',
    SyncOperation operation = SyncOperation.create,
    Map<String, dynamic>? payload,
  }) => stack.queue.enqueue(
    scope: scope,
    entityType: EntityCatalog.order,
    entityId: entityId,
    operation: operation,
    method: method,
    path: path,
    payload: payload,
  );

  test('entrega na ordem em que as operações foram criadas (FIFO)', () async {
    await enqueue(path: '/orders/', entityId: 'o1');
    await enqueue(path: '/orders/o1/items/', entityId: 'o1');
    await enqueue(path: '/orders/o1/close/', entityId: 'o1');

    final order = <String>[];
    for (var i = 0; i < 3; i++) {
      final claimed = await stack.queue.claimNext(scope: scope);
      order.add(claimed!.path);
      await stack.queue.markSynced(claimed.id);
    }

    expect(order, [
      '/orders/',
      '/orders/o1/items/',
      '/orders/o1/close/',
    ]);
  });

  test('a própria criação com ID temporário é entregável', () async {
    // Sem esta garantia a fila travaria de saída: a operação que CRIA o
    // identificador temporário seria confundida com uma que depende dele.
    await enqueue(path: '/orders/', entityId: 'offline-novo');

    final claimed = await stack.queue.claimNext(scope: scope);

    expect(claimed, isNotNull);
    expect(claimed!.entityId, 'offline-novo');
  });

  test('quem depende de uma criação que não subiu espera a sua vez', () async {
    await enqueue(path: '/orders/', entityId: 'offline-pedido');
    await enqueue(
      path: '/orders/offline-pedido/items/',
      entityId: 'offline-pedido',
      operation: SyncOperation.update,
    );

    final first = await stack.queue.claimNext(scope: scope);
    expect(first!.path, '/orders/');

    // A criação ainda está reservada (em voo): a inclusão do item não pode
    // sair na frente referenciando um pedido que o servidor não conhece.
    final second = await stack.queue.claimNext(scope: scope);
    expect(second, isNull);

    await stack.queue.registerResolvedId(
      scope: scope,
      localId: 'offline-pedido',
      remoteId: 'pedido-real',
    );
    await stack.queue.markSynced(first.id);

    final third = await stack.queue.claimNext(scope: scope);
    expect(third!.path, '/orders/pedido-real/items/');
  });

  test('uma operação independente passa na frente de uma recusada', () async {
    // FIFO cego travaria a loja inteira: uma venda recusada por regra de
    // negócio seguraria todas as outras até alguém resolver na mão.
    final bloqueada = await enqueue(path: '/orders/', entityId: 'o1');
    await enqueue(path: '/customers/', entityId: 'c1');

    final first = await stack.queue.claimNext(scope: scope);
    expect(first!.operationId, bloqueada);
    await stack.queue.markFailed(first.id, error: 'Comanda inexistente.');

    final second = await stack.queue.claimNext(scope: scope);
    expect(second!.path, '/customers/');
  });

  test('cada operação carrega um identificador único de idempotência', () async {
    final a = await enqueue(path: '/orders/', entityId: 'o1');
    final b = await enqueue(path: '/orders/', entityId: 'o2');

    expect(a, isNot(b));
    expect(a, matches(RegExp(r'^[0-9a-f-]{36}$')));

    // Reenfileirar a MESMA operação não cria uma segunda entrada.
    await stack.queue.enqueue(
      scope: scope,
      entityType: EntityCatalog.order,
      entityId: 'o1',
      operation: SyncOperation.create,
      method: 'POST',
      path: '/orders/',
      operationId: a,
    );
    expect(await stack.queue.entries(scope: scope), hasLength(2));
  });

  test('backoff segue a escada 5s, 15s, 30s, 1min, 5min e repete o teto', () {
    expect(SyncQueueService.backoffFor(1), const Duration(seconds: 5));
    expect(SyncQueueService.backoffFor(2), const Duration(seconds: 15));
    expect(SyncQueueService.backoffFor(3), const Duration(seconds: 30));
    expect(SyncQueueService.backoffFor(4), const Duration(minutes: 1));
    expect(SyncQueueService.backoffFor(5), const Duration(minutes: 5));
    expect(SyncQueueService.backoffFor(9), const Duration(minutes: 5));
  });

  test('erro temporário volta para a fila; erro definitivo sai da rotação', () async {
    final temporaria = await enqueue(path: '/orders/', entityId: 'o1');
    final definitiva = await enqueue(path: '/customers/', entityId: 'c1');

    final first = await stack.queue.claimNext(scope: scope);
    await stack.queue.markRetry(
      first!.id,
      attempts: 1,
      error: 'Tempo esgotado.',
    );
    final second = await stack.queue.claimNext(scope: scope);
    await stack.queue.markFailed(second!.id, error: 'HTTP 400.');

    final entries = await stack.queue.entries(scope: scope);
    final byId = {for (final entry in entries) entry.operationId: entry};
    expect(byId[temporaria]!.status, SyncQueueStatus.pending);
    expect(byId[temporaria]!.nextRetryAt, isNotNull);
    expect(byId[definitiva]!.status, SyncQueueStatus.failed);

    final summary = await stack.queue.summary(scope: scope);
    expect(summary.pending, 1);
    expect(summary.failed, 1);
  });

  test('reservar impede que dois processos enviem a mesma operação', () async {
    await enqueue(path: '/orders/', entityId: 'o1');

    final primeiro = await stack.queue.claimNext(scope: scope);
    final segundo = await stack.queue.claimNext(scope: scope);

    expect(primeiro, isNotNull);
    expect(segundo, isNull);
  });

  test('descartar uma recusada leva junto o que dependia dela', () async {
    await enqueue(path: '/orders/', entityId: 'offline-pedido');
    await enqueue(
      path: '/orders/offline-pedido/items/',
      entityId: 'offline-pedido',
      operation: SyncOperation.update,
    );

    final raiz = await stack.queue.claimNext(scope: scope);
    await stack.queue.markFailed(raiz!.id, error: 'Recusada.');

    expect(await stack.queue.discardFailed(raiz.id), isTrue);
    // Manter o item deixaria a fila tentando alterar para sempre um pedido
    // que nunca vai existir no servidor.
    expect(await stack.queue.entries(scope: scope), isEmpty);
  });

  test('não descarta uma operação que ainda pode ser entregue', () async {
    await enqueue(path: '/orders/', entityId: 'o1');
    final entries = await stack.queue.entries(scope: scope);

    expect(await stack.queue.discardFailed(entries.single.id), isFalse);
    expect(await stack.queue.entries(scope: scope), hasLength(1));
  });

  test('corrige o corpo de uma operação que ainda está na fila', () async {
    final id = await enqueue(
      path: '/orders/o1/send-to-kitchen/',
      payload: {'client_batch_serial': 'lote-1'},
    );

    expect(await stack.queue.patchPayload(id, {'offline_printed': true}), isTrue);

    final entry = (await stack.queue.entries(scope: scope)).single;
    expect(entry.payload!['client_batch_serial'], 'lote-1');
    expect(entry.payload!['offline_printed'], isTrue);
    expect(await stack.queue.patchPayload('inexistente', const {}), isFalse);
  });

  test('resolver referências reescreve caminho e corpo pendentes', () async {
    await stack.queue.registerResolvedId(
      scope: scope,
      localId: 'offline-pedido',
      remoteId: 'pedido-real',
    );
    await enqueue(
      path: '/orders/offline-pedido/items/',
      entityId: 'offline-pedido',
      operation: SyncOperation.update,
      payload: {'order': 'offline-pedido', 'product': 'p1'},
    );

    final claimed = await stack.queue.claimNext(scope: scope);
    final resolved = await stack.queue.resolveReferences(
      claimed!,
      scope: scope,
    );

    expect(resolved.path, '/orders/pedido-real/items/');
    expect(resolved.payload!['order'], 'pedido-real');
    expect(resolved.entityId, 'pedido-real');
  });
}
