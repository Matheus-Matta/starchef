import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';

/// `patchBody` existe para corrigir uma operação que já entrou na fila
/// offline antes de descobrirmos um detalhe que só ficou claro depois (ex.:
/// a comanda de cozinha já saiu impressa localmente) — sem isto, quando a
/// fila sincroniza, o servidor não sabe disso e manda imprimir de novo.
void main() {
  late Directory directory;
  late OfflineStore store;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-offline-store');
    store = OfflineStore(
      file: File('${directory.path}${Platform.pathSeparator}offline.sqlite'),
      legacyFile: File(
        '${directory.path}${Platform.pathSeparator}offline_legacy.json',
      ),
    );
  });

  tearDown(() async {
    await store.close();
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // Arquivo pode ficar preso por instantes no Windows.
    }
  });

  test('acrescenta campos ao corpo de uma operação ainda na fila', () async {
    await store.enqueue({
      'queue_id': 'op-1',
      'scope': 'conta-1',
      'method': 'POST',
      'path': '/orders/pedido-1/send-to-kitchen/',
      'body': {'client_batch_serial': 'batch-1'},
    });

    await store.patchBody('op-1', {'offline_printed': true});

    final rows = await store.pending(scope: 'conta-1');
    expect(rows.single['body'], {
      'client_batch_serial': 'batch-1',
      'offline_printed': true,
    });
  });

  test('não faz nada quando a operação já saiu da fila', () async {
    await store.enqueue({
      'queue_id': 'op-1',
      'scope': 'conta-1',
      'method': 'POST',
      'path': '/orders/pedido-1/send-to-kitchen/',
      'body': {'client_batch_serial': 'batch-1'},
    });
    await store.remove('op-1');

    // Não deve lançar mesmo sem a linha existir mais.
    await store.patchBody('op-1', {'offline_printed': true});

    expect(await store.pending(scope: 'conta-1'), isEmpty);
  });
}
