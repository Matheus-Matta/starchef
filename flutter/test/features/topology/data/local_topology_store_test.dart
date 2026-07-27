import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/topology/data/local_topology_store.dart';
import 'package:starchef_pdv/features/topology/domain/local_topology_config.dart';

void main() {
  group('LocalTopologyStore', () {
    late Directory temporaryDirectory;
    late File databaseFile;
    late _MemorySecretStorage secrets;
    LocalTopologyStore? store;

    setUp(() async {
      temporaryDirectory = await Directory.systemTemp.createTemp(
        'starchef-topology-',
      );
      databaseFile = File(
        '${temporaryDirectory.path}${Platform.pathSeparator}topology.sqlite',
      );
      secrets = _MemorySecretStorage();
    });

    tearDown(() async {
      await store?.close();
      await _deleteTemporaryDirectory(temporaryDirectory);
    });

    test('persists device configuration and secret separately', () async {
      store = LocalTopologyStore(
        file: databaseFile,
        secretStorage: secrets,
      );
      final initial = await store!.load();
      final configured = initial.copyWith(
        mode: LocalTopologyMode.principal,
        port: 49110,
        pairingSecret: LocalTopologyStore.generatePairingSecret(),
        trustedNetworkAcknowledged: true,
      );

      await store!.save(configured);
      await store!.close();
      store = LocalTopologyStore(
        file: databaseFile,
        secretStorage: secrets,
      );
      final restored = await store!.load();

      expect(restored.mode, LocalTopologyMode.principal);
      expect(restored.nodeId, initial.nodeId);
      expect(restored.port, 49110);
      expect(restored.pairingSecret, configured.pairingSecret);
      expect(restored.trustedNetworkAcknowledged, isTrue);
    });

    test('receipt is idempotent only for the same request hash', () async {
      store = LocalTopologyStore(
        file: databaseFile,
        secretStorage: secrets,
      );
      await store!.saveReceipt(
        accountId: 'account-1',
        nodeId: 'node-1',
        operationId: 'operation-1',
        requestHash: 'hash-a',
        response: const {'id': 'order-1'},
      );

      expect(
        await store!.receipt(
          accountId: 'account-1',
          nodeId: 'node-1',
          operationId: 'operation-1',
          requestHash: 'hash-a',
        ),
        const {'id': 'order-1'},
      );
      await expectLater(
        store!.receipt(
          accountId: 'account-1',
          nodeId: 'node-1',
          operationId: 'operation-1',
          requestHash: 'hash-b',
        ),
        throwsA(isA<LocalRelayReceiptConflict>()),
      );
    });

    test('nonce survives restart and cannot be consumed twice', () async {
      store = LocalTopologyStore(
        file: databaseFile,
        secretStorage: secrets,
      );
      final now = DateTime.now().toUtc();
      expect(
        await store!.consumeNonce(
          accountId: 'account-1',
          nodeId: 'node-1',
          nonce: 'nonce-123456',
          seenAt: now,
          expiresBefore: now.subtract(const Duration(minutes: 2)),
        ),
        isTrue,
      );
      await store!.close();
      store = LocalTopologyStore(
        file: databaseFile,
        secretStorage: secrets,
      );

      expect(
        await store!.consumeNonce(
          accountId: 'account-1',
          nodeId: 'node-1',
          nonce: 'nonce-123456',
          seenAt: now.add(const Duration(seconds: 1)),
          expiresBefore: now.subtract(const Duration(minutes: 2)),
        ),
        isFalse,
      );
    });
  });
}

class _MemorySecretStorage implements TopologySecretStorage {
  String? value;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String value) async => this.value = value;
}

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
