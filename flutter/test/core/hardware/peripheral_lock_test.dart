import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/hardware/peripheral_lock.dart';
import 'package:starchef_pdv/core/storage/app_paths.dart';

void main() {
  late Directory directory;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-peripheral');
    AppPaths.overrideDataDirectory(directory);
  });

  tearDown(() async {
    AppPaths.overrideDataDirectory(null);
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // O arquivo pode continuar preso por instantes no Windows.
    }
  });

  test('sem concorrência, entra na fila e sai com a trava na hora', () async {
    final lock = await PeripheralLock.acquireQueued(
      'printer:COM1',
      role: 'impressora',
    );

    expect(lock, isNotNull);
    await lock!.release();
  });

  test(
    'quem entra na fila primeiro sai primeiro, mesmo pedindo depois de quem já espera',
    () async {
      // Segura a trava real para forçar os dois pedidos seguintes a ficarem
      // na fila de bilhetes.
      final holder = await PeripheralLock.tryAcquire(
        'printer:COM1',
        role: 'segurando',
      );
      expect(holder, isNotNull);

      final order = <String>[];
      final first = PeripheralLock.acquireQueued(
        'printer:COM1',
        role: 'primeiro',
        timeout: const Duration(seconds: 3),
      ).then((lock) => order.add('primeiro'));
      // Só entra na fila depois que o "primeiro" já tem bilhete emitido —
      // sem essa espera, os dois poderiam empatar no mesmo microssegundo em
      // máquinas rápidas e o teste ficaria instável.
      await Future<void>.delayed(const Duration(milliseconds: 20));
      final second = PeripheralLock.acquireQueued(
        'printer:COM1',
        role: 'segundo',
        timeout: const Duration(seconds: 3),
      ).then((lock) => order.add('segundo'));

      // Solta a trava real depois que os dois já estão esperando: nenhum dos
      // dois deveria conseguir antes disso.
      await Future<void>.delayed(const Duration(milliseconds: 60));
      expect(order, isEmpty);
      await holder!.release();

      await Future.wait([first, second]);
      expect(order, ['primeiro', 'segundo']);
    },
  );

  test('bilhete abandonado (processo morto) não trava a fila', () async {
    // Simula um bilhete de um processo que caiu antes de limpar: arquivo
    // antigo, sem ninguém para apagá-lo.
    final ticketsDir = Directory(
      '${directory.path}${Platform.pathSeparator}locks'
      '${Platform.pathSeparator}printer_com1.waiting',
    );
    await ticketsDir.create(recursive: true);
    final stale = File(
      '${ticketsDir.path}${Platform.pathSeparator}1-99999-0',
    );
    await stale.writeAsString('99999');
    await stale.setLastModified(
      DateTime.now().subtract(const Duration(minutes: 5)),
    );

    final lock = await PeripheralLock.acquireQueued(
      'printer:COM1',
      role: 'impressora',
      ticketTtl: const Duration(seconds: 10),
      timeout: const Duration(seconds: 2),
    );

    expect(lock, isNotNull);
    await lock!.release();
  });

  test('desiste depois do timeout se ninguém libera a trava', () async {
    final holder = await PeripheralLock.tryAcquire(
      'printer:COM1',
      role: 'segurando',
    );
    addTearDown(() => holder?.release());

    final lock = await PeripheralLock.acquireQueued(
      'printer:COM1',
      role: 'impaciente',
      timeout: const Duration(milliseconds: 200),
      pollInterval: const Duration(milliseconds: 20),
    );

    expect(lock, isNull);
  });
}
