import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/scale/data/scanner_binding_store.dart';

void main() {
  group('ScannerBindingStore', () {
    late Directory temporaryDirectory;
    late File databaseFile;
    ScannerBindingStore? store;

    setUp(() async {
      temporaryDirectory = await Directory.systemTemp.createTemp(
        'starchef-scanner-bindings-',
      );
      databaseFile = File(
        '${temporaryDirectory.path}${Platform.pathSeparator}bindings.sqlite',
      );
    });

    tearDown(() async {
      await store?.close();
      await _deleteTemporaryDirectory(temporaryDirectory);
    });

    test('persists every hardware identity field after reopening', () async {
      store = ScannerBindingStore(file: databaseFile);
      await store!.save(_binding());
      await store!.close();

      store = ScannerBindingStore(file: databaseFile);
      final restored = await store!.read('restaurant-1:scale-1');

      expect(restored, isNotNull);
      expect(restored!.slot, 'restaurant-1:scale-1');
      expect(restored.portName, 'COM7');
      expect(restored.baudRate, 115200);
      expect(restored.vendorId, 0x1234);
      expect(restored.productId, 0xABCD);
      expect(restored.serialNumber, 'SCANNER-001');
      expect(restored.productName, 'Scanner do balcão');
    });

    test('updates the binding associated with an existing slot', () async {
      store = ScannerBindingStore(file: databaseFile);
      await store!.save(_binding());

      await store!.save(
        const ScannerBinding(
          slot: 'restaurant-1:scale-1',
          portName: 'COM9',
          baudRate: 9600,
          vendorId: 0x4321,
          productId: 0xDCBA,
          serialNumber: 'SCANNER-002',
          productName: 'Scanner reserva',
        ),
      );

      final updated = await store!.read('restaurant-1:scale-1');
      expect(updated, isNotNull);
      expect(updated!.portName, 'COM9');
      expect(updated.baudRate, 9600);
      expect(updated.vendorId, 0x4321);
      expect(updated.productId, 0xDCBA);
      expect(updated.serialNumber, 'SCANNER-002');
      expect(updated.productName, 'Scanner reserva');
    });

    test('clears only the requested slot', () async {
      store = ScannerBindingStore(file: databaseFile);
      await store!.save(_binding());
      await store!.save(
        const ScannerBinding(
          slot: 'restaurant-1:scale-2',
          portName: 'COM8',
          baudRate: 9600,
        ),
      );

      await store!.clear('restaurant-1:scale-1');

      expect(await store!.read('restaurant-1:scale-1'), isNull);
      expect(await store!.read('restaurant-1:scale-2'), isNotNull);
    });

    test('does not allow two slots to reserve the same serial port', () async {
      store = ScannerBindingStore(file: databaseFile);
      await store!.save(_binding());

      await expectLater(
        store!.save(
          const ScannerBinding(
            slot: 'restaurant-2:scale-9',
            portName: 'COM7',
            baudRate: 9600,
          ),
        ),
        throwsA(
          predicate<Object>(
            (error) =>
                error.toString().contains('UNIQUE constraint failed') &&
                error.toString().contains('scanner_bindings.port_name'),
          ),
        ),
      );

      expect(await store!.read('restaurant-1:scale-1'), isNotNull);
      expect(await store!.read('restaurant-2:scale-9'), isNull);
    });
  });
}

ScannerBinding _binding() => const ScannerBinding(
  slot: 'restaurant-1:scale-1',
  portName: 'COM7',
  baudRate: 115200,
  vendorId: 0x1234,
  productId: 0xABCD,
  serialNumber: 'SCANNER-001',
  productName: 'Scanner do balcão',
);

Future<void> _deleteTemporaryDirectory(Directory directory) async {
  for (var attempt = 0; attempt < 5; attempt++) {
    try {
      await directory.delete(recursive: true);
      return;
    } on FileSystemException {
      if (attempt == 4) rethrow;
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
  }
}
