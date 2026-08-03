import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';

void main() {
  late Directory directory;
  late OfflineStore store;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-outbox');
    store = OfflineStore(
      file: File('${directory.path}${Platform.pathSeparator}outbox.sqlite'),
    );
  });

  tearDown(() async {
    await store.close();
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // O arquivo pode continuar preso por instantes no Windows.
    }
  });

  Future<void> enqueue(String queueId) => store.enqueue({
    'queue_id': queueId,
    'scope': 'terminal',
    'method': 'POST',
    'path': '/orders/',
    'body': {'restaurant': 'r1'},
    'idempotency_key': queueId,
    'created_at': DateTime.now().toUtc().toIso8601String(),
  });

  test('uma operação bloqueada volta para a fila mantendo a chave', () async {
    await enqueue('op-1');
    await store.markBlocked('op-1', error: 'Comanda não encontrada.');
    expect((await store.summary(scope: 'terminal')).blocked, 1);

    await store.unblock('op-1');

    final summary = await store.summary(scope: 'terminal');
    expect(summary.blocked, 0);
    expect(summary.pending, 1);

    final item = (await store.pending(scope: 'terminal')).single;
    expect(item['state'], 'pending');
    expect(item['attempt_count'], 0);
    expect(item['last_error'], isNull);
    // A chave precisa sobreviver: sem ela o reenvio criaria uma segunda venda.
    expect(item['idempotency_key'], 'op-1');
  });

  test('descartar remove definitivamente uma operação bloqueada', () async {
    await enqueue('op-2');
    await store.markBlocked('op-2', error: 'Caixa fechado.');

    final removed = await store.discardBlocked('op-2');

    expect(removed, isTrue);
    expect((await store.summary(scope: 'terminal')).total, 0);
  });

  test('uma operação ainda na fila não pode ser descartada', () async {
    await enqueue('op-3');

    final removed = await store.discardBlocked('op-3');

    // Ela pode estar sendo enviada neste instante; apagá-la perderia a venda.
    expect(removed, isFalse);
    expect((await store.summary(scope: 'terminal')).pending, 1);
  });

  test('uma operação em retry também é protegida do descarte', () async {
    await enqueue('op-4');
    await store.markRetry(
      'op-4',
      attemptCount: 2,
      nextAttemptAt: DateTime.now().toUtc().add(const Duration(minutes: 1)),
      error: 'Servidor indisponível.',
    );

    expect(await store.discardBlocked('op-4'), isFalse);
    expect((await store.summary(scope: 'terminal')).retrying, 1);
  });

  test('desbloquear algo que não está bloqueado não muda nada', () async {
    await enqueue('op-5');
    await store.markRetry(
      'op-5',
      attemptCount: 3,
      nextAttemptAt: DateTime.now().toUtc().add(const Duration(minutes: 5)),
      error: 'timeout',
    );

    await store.unblock('op-5');

    final item = (await store.pending(scope: 'terminal')).single;
    expect(item['state'], 'retry');
    expect(item['attempt_count'], 3);
  });
}
