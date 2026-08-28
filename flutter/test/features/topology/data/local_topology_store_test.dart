import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqlite_async/sqlite_async.dart';
import 'package:starchef_pdv/core/storage/durable_secure_store.dart';
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
      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
      final initial = await store!.load();
      final configured = initial.copyWith(
        mode: LocalTopologyMode.principal,
        port: 49110,
        pairingSecret: LocalTopologyStore.generatePairingSecret(),
        trustedNetworkAcknowledged: true,
      );

      await store!.save(configured);
      await store!.close();
      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
      final restored = await store!.load();

      expect(restored.mode, LocalTopologyMode.principal);
      expect(restored.nodeId, initial.nodeId);
      expect(restored.port, 49110);
      expect(restored.pairingSecret, configured.pairingSecret);
      expect(restored.trustedNetworkAcknowledged, isTrue);
    });

    test('instalação nova nasce secundária, sem principal definido', () async {
      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);

      final fresh = await store!.load();

      // Ser o principal é decisão da loja, não acidente da instalação: se todo
      // terminal novo subisse como principal, o segundo caixa instalado viraria
      // um segundo principal sincronizando por conta própria com a nuvem.
      expect(fresh.mode, LocalTopologyMode.client);
      expect(fresh.principalHost, isEmpty);
      // Fica bloqueado até alguém dizer qual é o papel dele.
      expect(fresh.validate(), isNotEmpty);

      // A chave já vem pronta para quando ele for promovido a principal.
      expect(fresh.pairingSecret, isNotEmpty);
      expect(fresh.trustedNetworkAcknowledged, isTrue);
      expect(fresh.lanSharingErrors(), isEmpty);
    });

    test('promover a principal não exige mais nenhuma configuração', () async {
      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
      final fresh = await store!.load();

      final asPrincipal = fresh.copyWith(mode: LocalTopologyMode.principal);

      // A decisão é um clique: chave e confirmação de rede já vieram prontas.
      expect(asPrincipal.validate(), isEmpty);
      expect(asPrincipal.lanSharingErrors(), isEmpty);
    });

    test('a chave gerada sozinha sobrevive ao reinício', () async {
      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
      final first = await store!.load();
      await store!.close();

      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
      final second = await store!.load();

      // Gerar outra a cada boot deixaria os secundários fora do ar.
      expect(second.pairingSecret, first.pairingSecret);
      expect(second.nodeId, first.nodeId);
    });

    test('a chave sobrevive sem keyring usando o fallback do Linux', () async {
      final fallbackDirectory = Directory(
        '${temporaryDirectory.path}${Platform.pathSeparator}secure',
      );
      SecureTopologySecretStorage secretStorage() =>
          SecureTopologySecretStorage(
            valueStore: DurableSecureStore(
              primary: _UnavailableSecureValueStore(),
              fallback: OwnerProtectedFileValueStore(
                directory: fallbackDirectory,
                enforceModes: false,
              ),
            ),
          );
      store = LocalTopologyStore(
        file: databaseFile,
        secretStorage: secretStorage(),
      );
      final first = await store!.load();
      await store!.close();

      store = LocalTopologyStore(
        file: databaseFile,
        secretStorage: secretStorage(),
      );
      final second = await store!.load();

      expect(second.pairingSecret, first.pairingSecret);
      expect(second.nodeId, first.nodeId);
    });

    test(
      'instalação antiga em standalone é promovida a principal ativo',
      () async {
        // Cria o banco no formato antigo e força o estado que existia lá.
        store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
        await store!.load();
        await store!.close();
        await _forceLegacyStandalone(databaseFile);

        store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
        final migrated = await store!.load();

        // Naquele modo os campos de rede nem apareciam, então o zero ali
        // significava "nunca configurado", não "o operador desligou".
        expect(migrated.mode, LocalTopologyMode.principal);
        expect(migrated.trustedNetworkAcknowledged, isTrue);
        expect(migrated.lanSharingErrors(), isEmpty);
      },
    );

    test('receipt is idempotent only for the same request hash', () async {
      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
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

    test('recibos antigos saem, os recentes continuam protegendo', () async {
      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
      final now = DateTime.now();

      // Um recibo do mês passado: nenhum caixa cliente ainda tenta reenviar
      // uma operação tão velha, e mantê-lo só faz a tabela crescer.
      await store!.saveReceipt(
        accountId: 'account-1',
        nodeId: 'node-1',
        operationId: 'operation-antiga',
        requestHash: 'hash-a',
        response: const {'id': 'order-antiga'},
        at: now.subtract(const Duration(days: 30)),
      );
      // Um de ontem: ainda dentro da janela em que um terminal que passou o
      // fim de semana fora pode voltar com a fila cheia.
      await store!.saveReceipt(
        accountId: 'account-1',
        nodeId: 'node-1',
        operationId: 'operation-recente',
        requestHash: 'hash-b',
        response: const {'id': 'order-recente'},
        at: now.subtract(const Duration(days: 1)),
      );

      // A limpeza roda na gravação seguinte.
      await store!.saveReceipt(
        accountId: 'account-1',
        nodeId: 'node-1',
        operationId: 'operation-nova',
        requestHash: 'hash-c',
        response: const {'id': 'order-nova'},
      );

      expect(
        await store!.receipt(
          accountId: 'account-1',
          nodeId: 'node-1',
          operationId: 'operation-antiga',
          requestHash: 'hash-a',
        ),
        isNull,
      );
      // Este precisa sobreviver: apagá-lo reabriria a janela de duplicidade.
      expect(
        await store!.receipt(
          accountId: 'account-1',
          nodeId: 'node-1',
          operationId: 'operation-recente',
          requestHash: 'hash-b',
        ),
        const {'id': 'order-recente'},
      );
    });

    test('nonce survives restart and cannot be consumed twice', () async {
      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);
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
      store = LocalTopologyStore(file: databaseFile, secretStorage: secrets);

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

class _UnavailableSecureValueStore implements SecureValueStore {
  @override
  Future<void> delete(String key) => throw StateError('keyring indisponível');

  @override
  Future<String?> read(String key) => throw StateError('keyring indisponível');

  @override
  Future<void> write(String key, String value) =>
      throw StateError('keyring indisponível');
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

/// Recria o estado de uma instalação anterior à remoção do modo independente:
/// `standalone` com a rede nunca confirmada.
Future<void> _forceLegacyStandalone(File databaseFile) async {
  final database = SqliteDatabase(path: databaseFile.path);
  try {
    await database.execute('''
      UPDATE local_topology_config
      SET mode = 'standalone', trusted_network = 0
      WHERE singleton_id = 1
    ''');
    // Volta a versão do schema para que a migração rode de novo na abertura.
    await database.execute('DELETE FROM _migrations WHERE id >= 2');
  } finally {
    await database.close();
  }
}
