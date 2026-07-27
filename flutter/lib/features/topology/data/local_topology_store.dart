import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:sqlite_async/sqlite_async.dart';

import '../domain/local_topology_config.dart';

abstract interface class TopologySecretStorage {
  Future<String?> read();
  Future<void> write(String value);
}

class SecureTopologySecretStorage implements TopologySecretStorage {
  SecureTopologySecretStorage({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'starchef_local_topology_pairing_secret';
  final FlutterSecureStorage _storage;

  @override
  Future<String?> read() => _storage.read(key: _key);

  @override
  Future<void> write(String value) => _storage.write(key: _key, value: value);
}

class LocalTopologyStore {
  LocalTopologyStore({
    File? file,
    TopologySecretStorage? secretStorage,
  }) : _file = file ?? _defaultFile(),
       _secretStorage = secretStorage ?? SecureTopologySecretStorage() {
    _database = SqliteDatabase(path: _file.path);
    _ready = _initialize();
  }

  static const _schemaVersion = 1;

  final File _file;
  final TopologySecretStorage _secretStorage;
  late final SqliteDatabase _database;
  late final Future<void> _ready;
  bool _closed = false;

  static File _defaultFile() {
    final configured = Platform.environment['LOCALAPPDATA'];
    final base = configured == null || configured.trim().isEmpty
        ? Directory.systemTemp.path
        : configured;
    return File(
      '$base${Platform.pathSeparator}StarChef'
      '${Platform.pathSeparator}local_topology.sqlite',
    );
  }

  static String generateNodeId() => _randomToken(12);

  static String generatePairingSecret() => _randomToken(32);

  static String _randomToken(int byteCount) {
    final random = Random.secure();
    final bytes = List<int>.generate(byteCount, (_) => random.nextInt(256));
    return base64UrlEncode(bytes).replaceAll('=', '');
  }

  Future<void> _initialize() async {
    await _file.parent.create(recursive: true);
    final migrations = SqliteMigrations()
      ..createDatabase = SqliteMigration(_schemaVersion, _createSchema)
      ..add(SqliteMigration(_schemaVersion, _createSchema));
    await migrations.migrate(_database);
  }

  static Future<void> _createSchema(SqliteWriteContext tx) async {
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS local_topology_config (
        singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
        mode TEXT NOT NULL,
        node_id TEXT NOT NULL,
        principal_host TEXT NOT NULL DEFAULT '',
        port INTEGER NOT NULL,
        trusted_network INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
      )
    ''');
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS local_relay_receipts (
        account_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        response_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY(account_id, operation_id)
      )
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS local_relay_receipts_created_idx
      ON local_relay_receipts(created_at)
    ''');
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS local_relay_nonces (
        account_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        nonce TEXT NOT NULL,
        seen_at INTEGER NOT NULL,
        PRIMARY KEY(account_id, node_id, nonce)
      )
    ''');
  }

  Future<LocalTopologyConfig> load() async {
    await _ready;
    var row = await _database.getOptional(
      'SELECT * FROM local_topology_config WHERE singleton_id = 1',
    );
    if (row == null) {
      final nodeId = generateNodeId();
      await _database.execute(
        '''
        INSERT INTO local_topology_config(
          singleton_id, mode, node_id, principal_host, port, updated_at
        ) VALUES (1, 'standalone', ?, '', ?, ?)
        ON CONFLICT(singleton_id) DO NOTHING
        ''',
        [
          nodeId,
          LocalTopologyConfig.defaultPort,
          DateTime.now().toUtc().toIso8601String(),
        ],
      );
      row = await _database.getOptional(
        'SELECT * FROM local_topology_config WHERE singleton_id = 1',
      );
    }
    final secret = await _secretStorage.read() ?? '';
    return LocalTopologyConfig(
      mode: LocalTopologyConfig.modeFrom(row?['mode']?.toString()),
      nodeId: '${row?['node_id'] ?? generateNodeId()}',
      principalHost: '${row?['principal_host'] ?? ''}',
      port:
          (row?['port'] as num?)?.toInt() ??
          LocalTopologyConfig.defaultPort,
      pairingSecret: secret,
      trustedNetworkAcknowledged:
          (row?['trusted_network'] as num?)?.toInt() == 1,
    );
  }

  Future<void> save(LocalTopologyConfig config) async {
    final errors = config.validate();
    if (errors.isNotEmpty) throw ArgumentError(errors.join(' '));
    await _ready;
    final previousSecret = await _secretStorage.read();
    await _secretStorage.write(config.pairingSecret.trim());
    try {
      await _database.execute(
        '''
        INSERT INTO local_topology_config(
          singleton_id, mode, node_id, principal_host, port, trusted_network,
          updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(singleton_id) DO UPDATE SET
          mode = excluded.mode,
          node_id = excluded.node_id,
          principal_host = excluded.principal_host,
          port = excluded.port,
          trusted_network = excluded.trusted_network,
          updated_at = excluded.updated_at
        ''',
        [
          config.mode.storageValue,
          config.nodeId,
          config.principalHost.trim(),
          config.port,
          config.trustedNetworkAcknowledged ? 1 : 0,
          DateTime.now().toUtc().toIso8601String(),
        ],
      );
    } catch (_) {
      await _secretStorage.write(previousSecret ?? '');
      rethrow;
    }
  }

  Future<Map<String, dynamic>?> receipt({
    required String accountId,
    required String nodeId,
    required String operationId,
    required String requestHash,
  }) async {
    await _ready;
    if (nodeId.trim().isEmpty) return null;
    final row = await _database.getOptional(
      '''
      SELECT request_hash, response_json FROM local_relay_receipts
      WHERE account_id = ? AND operation_id = ?
      ''',
      [accountId, operationId],
    );
    if (row == null) return null;
    if ('${row['request_hash']}' != requestHash) {
      throw const LocalRelayReceiptConflict();
    }
    final decoded = jsonDecode('${row['response_json']}');
    return decoded is Map ? Map<String, dynamic>.from(decoded) : null;
  }

  Future<void> saveReceipt({
    required String accountId,
    required String nodeId,
    required String operationId,
    required String requestHash,
    required Map<String, dynamic> response,
  }) async {
    await _ready;
    await _database.writeTransaction((tx) async {
      await tx.execute(
        '''
        INSERT INTO local_relay_receipts(
          account_id, node_id, operation_id, request_hash, response_json,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, operation_id) DO NOTHING
        ''',
        [
          accountId,
          nodeId,
          operationId,
          requestHash,
          jsonEncode(response),
          DateTime.now().millisecondsSinceEpoch,
        ],
      );
    });
    await receipt(
      accountId: accountId,
      nodeId: nodeId,
      operationId: operationId,
      requestHash: requestHash,
    );
  }

  Future<bool> consumeNonce({
    required String accountId,
    required String nodeId,
    required String nonce,
    required DateTime seenAt,
    required DateTime expiresBefore,
  }) async {
    await _ready;
    return _database.writeTransaction((tx) async {
      await tx.execute(
        'DELETE FROM local_relay_nonces WHERE seen_at < ?',
        [expiresBefore.toUtc().millisecondsSinceEpoch],
      );
      final existing = await tx.getOptional(
        '''
        SELECT nonce FROM local_relay_nonces
        WHERE account_id = ? AND node_id = ? AND nonce = ?
        ''',
        [accountId, nodeId, nonce],
      );
      if (existing != null) return false;
      await tx.execute(
        '''
        INSERT INTO local_relay_nonces(account_id, node_id, nonce, seen_at)
        VALUES (?, ?, ?, ?)
        ''',
        [
          accountId,
          nodeId,
          nonce,
          seenAt.toUtc().millisecondsSinceEpoch,
        ],
      );
      return true;
    });
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    await _ready;
    await _database.close();
  }
}

class LocalRelayReceiptConflict implements Exception {
  const LocalRelayReceiptConflict();

  @override
  String toString() =>
      'A chave da operação já foi usada com outro conteúdo.';
}
