import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/core/relay/pending_mutation.dart';
import 'package:starchef_garcom/core/storage/offline_queue_store.dart';

void main() {
  late Directory dir;
  late File file;

  setUp(() {
    dir = Directory.systemTemp.createTempSync('starchef-garcom-store-');
    file = File('${dir.path}${Platform.pathSeparator}outbox.json');
  });

  tearDown(() {
    if (dir.existsSync()) dir.deleteSync(recursive: true);
  });

  PendingMutation mutation(String id) => PendingMutation(
    operationId: id,
    method: 'POST',
    path: '/orders/pedido-1/items/',
    body: {'product': 'produto-1', 'quantity': 2},
    kind: 'add_item',
    summary: '2x Coxinha',
    createdAt: DateTime.utc(2026, 1, 1, 12, 30),
  );

  test('sem arquivo, carrega uma fila vazia', () async {
    final store = OfflineQueueStore(testFile: file);
    expect(await store.load(), isEmpty);
  });

  test('grava e relê preservando os campos', () async {
    final store = OfflineQueueStore(testFile: file);
    await store.save([mutation('op-1')]);

    final reloaded = await OfflineQueueStore(testFile: file).load();

    expect(reloaded, hasLength(1));
    final restored = reloaded.single;
    expect(restored.operationId, 'op-1');
    expect(restored.method, 'POST');
    expect(restored.path, '/orders/pedido-1/items/');
    expect(restored.body, {'product': 'produto-1', 'quantity': 2});
    expect(restored.kind, 'add_item');
    expect(restored.summary, '2x Coxinha');
    expect(restored.createdAt, DateTime.utc(2026, 1, 1, 12, 30));
  });

  test('sobrevive a fechar e abrir o app (arquivo persiste)', () async {
    await OfflineQueueStore(testFile: file).save([mutation('op-1'), mutation('op-2')]);

    // Uma instância nova simula o app reaberto: nada em memória, só o disco.
    final afterRestart = await OfflineQueueStore(testFile: file).load();

    expect(afterRestart.map((m) => m.operationId), ['op-1', 'op-2']);
  });

  test('salvar a fila vazia limpa o arquivo', () async {
    final store = OfflineQueueStore(testFile: file);
    await store.save([mutation('op-1')]);
    await store.save([]);

    expect(await OfflineQueueStore(testFile: file).load(), isEmpty);
  });

  test('arquivo corrompido carrega vazio em vez de travar', () async {
    await file.parent.create(recursive: true);
    await file.writeAsString('{não é json válido');

    expect(await OfflineQueueStore(testFile: file).load(), isEmpty);
  });

  test('gravações concorrentes não corrompem o arquivo', () async {
    final store = OfflineQueueStore(testFile: file);

    // Duas gravações disparadas ao mesmo tempo, sem esperar a primeira: o
    // encadeamento interno do store precisa serializar as duas de qualquer
    // forma (é o mesmo risco de uma tela lançando um item enquanto outra
    // pendência acaba de ser confirmada).
    await Future.wait([
      store.save([mutation('op-1')]),
      store.save([mutation('op-1'), mutation('op-2')]),
    ]);

    final result = await OfflineQueueStore(testFile: file).load();
    // O que importa é que o arquivo ficou legível e consistente com UMA das
    // duas gravações — nunca uma mistura corrompida das duas.
    expect(result.length, anyOf(1, 2));
  });

  test('retry() soma tentativas e guarda o último erro', () {
    final original = mutation('op-1');
    final retried = original.retry(error: 'timeout');

    expect(retried.attempts, 1);
    expect(retried.lastError, 'timeout');
    expect(retried.operationId, original.operationId, reason: 'id estável entre retentativas');

    final again = retried.retry(error: 'timeout de novo');
    expect(again.attempts, 2);
  });

  test('orderId e itemId são lidos do path', () {
    final add = PendingMutation(
      operationId: 'a',
      method: 'POST',
      path: '/orders/pedido-9/items/',
      kind: 'add_item',
      summary: 's',
      createdAt: DateTime.now(),
    );
    expect(add.orderId, 'pedido-9');
    expect(add.itemId, isNull);

    final void_ = PendingMutation(
      operationId: 'b',
      method: 'DELETE',
      path: '/orders/pedido-9/items/item-3/void/',
      kind: 'void_item',
      summary: 's',
      createdAt: DateTime.now(),
    );
    expect(void_.orderId, 'pedido-9');
    expect(void_.itemId, 'item-3');
  });
}
