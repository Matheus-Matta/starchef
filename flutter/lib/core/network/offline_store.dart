import 'dart:convert';
import 'dart:io';

import 'package:sqlite_async/sqlite_async.dart';

import '../storage/app_paths.dart';

/// SQLite-backed cache and transactional outbox used by the desktop PDV.
///
/// `sqlite_async` keeps database I/O off the UI isolate, enables WAL by
/// default and coordinates multiple engines using the same file. That makes
/// this store safe for the main checkout and independent scale windows.
class OfflineStore {
  OfflineStore({File? file, File? legacyFile})
    : _file = file ?? _defaultFile(),
      _legacyFile = legacyFile ?? (file == null ? _defaultLegacyFile() : null) {
    _database = SqliteDatabase(path: _file.path);
    _ready = _initialize();
  }

  static const _maxCacheEntries = 300;
  static const _schemaVersion = 2;

  final File _file;
  final File? _legacyFile;
  late final SqliteDatabase _database;
  late final Future<void> _ready;
  bool _closed = false;

  static File _defaultFile() => AppPaths.dataFile('offline_data.sqlite');

  static File _defaultLegacyFile() => AppPaths.dataFile('offline_data.json');

  Future<void> _initialize() async {
    await _file.parent.create(recursive: true);
    final migrations = SqliteMigrations()
      ..createDatabase = SqliteMigration(
        _schemaVersion,
        (tx) async => _createSchema(tx),
      )
      ..add(SqliteMigration(1, (tx) async => _createSchema(tx)))
      ..add(SqliteMigration(2, _addOutboxLeaseColumns));
    await migrations.migrate(_database);
    await _importLegacyJsonOnce();
  }

  static Future<void> _createSchema(SqliteWriteContext tx) async {
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS offline_cache (
        cache_key TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        updated_at INTEGER NOT NULL
      )
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS offline_cache_updated_idx
      ON offline_cache(updated_at)
    ''');
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS offline_outbox (
        queue_id TEXT PRIMARY KEY,
        scope TEXT NOT NULL,
        method TEXT NOT NULL,
        path TEXT NOT NULL,
        query_json TEXT,
        body_json TEXT,
        temporary_id TEXT,
        idempotency_key TEXT NOT NULL,
        created_at TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT,
        last_error TEXT,
        lease_owner TEXT,
        lease_until TEXT
      )
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS offline_outbox_dequeue_idx
      ON offline_outbox(scope, state, next_attempt_at, created_at)
    ''');
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS offline_id_map (
        scope TEXT NOT NULL,
        local_id TEXT NOT NULL,
        remote_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(scope, local_id)
      )
    ''');
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS offline_meta (
        meta_key TEXT PRIMARY KEY,
        meta_value TEXT NOT NULL
      )
    ''');
  }

  static Future<void> _addOutboxLeaseColumns(SqliteWriteContext tx) async {
    await tx.execute(
      'ALTER TABLE offline_outbox ADD COLUMN lease_owner TEXT',
    );
    await tx.execute(
      'ALTER TABLE offline_outbox ADD COLUMN lease_until TEXT',
    );
  }

  Future<Map<String, dynamic>?> cached(String key) async {
    await _ready;
    final row = await _database.getOptional(
      'SELECT payload FROM offline_cache WHERE cache_key = ?',
      [key],
    );
    if (row == null) return null;
    return _decodeMap(row['payload']);
  }

  Future<void> cache(String key, Map<String, dynamic> value) async {
    await _ready;
    final payload = jsonEncode(value);
    final current = await _database.getOptional(
      'SELECT payload FROM offline_cache WHERE cache_key = ?',
      [key],
    );
    if (current?['payload'] == payload) return;
    await _database.writeTransaction((tx) async {
      await tx.execute(
        '''
        INSERT INTO offline_cache(cache_key, payload, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
          payload = excluded.payload,
          updated_at = excluded.updated_at
        ''',
        [key, payload, DateTime.now().millisecondsSinceEpoch],
      );
      await tx.execute(
        '''
        DELETE FROM offline_cache
        WHERE cache_key IN (
          SELECT cache_key FROM offline_cache
          ORDER BY updated_at DESC
          LIMIT -1 OFFSET ?
        )
        ''',
        [_maxCacheEntries],
      );
    });
  }

  Future<List<Map<String, dynamic>>> pending({
    String? scope,
    int? limit,
    bool eligibleOnly = false,
    bool includeBlocked = true,
  }) async {
    await _ready;
    final clauses = <String>[];
    final parameters = <Object?>[];
    if (scope != null) {
      clauses.add('scope = ?');
      parameters.add(scope);
    }
    if (!includeBlocked) clauses.add("state != 'blocked'");
    if (eligibleOnly) {
      clauses.add("state IN ('pending', 'retry')");
      clauses.add('(next_attempt_at IS NULL OR next_attempt_at <= ?)');
      parameters.add(DateTime.now().toUtc().toIso8601String());
    }
    final where = clauses.isEmpty ? '' : 'WHERE ${clauses.join(' AND ')}';
    final capped = limit == null ? '' : 'LIMIT ?';
    if (limit != null) parameters.add(limit);
    final rows = await _database.getAll('''
      SELECT * FROM offline_outbox
      $where
      ORDER BY created_at, queue_id
      $capped
      ''', parameters);
    return rows.map(_outboxRow).toList();
  }

  Future<Map<String, dynamic>?> claimNext({
    required String scope,
    required String leaseOwner,
    Duration leaseDuration = const Duration(seconds: 30),
  }) async {
    await _ready;
    return _database.writeTransaction((tx) async {
      final now = DateTime.now().toUtc();
      final row = await tx.getOptional(
        '''
        SELECT queue_id, state, next_attempt_at, lease_until
        FROM offline_outbox
        WHERE scope = ?
        ORDER BY created_at, queue_id
        LIMIT 1
        ''',
        [scope],
      );
      if (row == null) return null;
      final state = '${row['state']}';
      if (state != 'pending' && state != 'retry') return null;
      final nextAttemptAt = DateTime.tryParse(
        '${row['next_attempt_at'] ?? ''}',
      )?.toUtc();
      if (nextAttemptAt != null && nextAttemptAt.isAfter(now)) return null;
      final leaseUntil = DateTime.tryParse(
        '${row['lease_until'] ?? ''}',
      )?.toUtc();
      if (leaseUntil != null && leaseUntil.isAfter(now)) return null;

      // Preserve causal order. Skipping a leased, delayed or blocked parent
      // could send a dependent item before its temporary order ID is mapped.
      final queueId = '${row['queue_id']}';
      await tx.execute(
        '''
        UPDATE offline_outbox
        SET lease_owner = ?, lease_until = ?
        WHERE queue_id = ?
        ''',
        [
          leaseOwner,
          now.add(leaseDuration).toIso8601String(),
          queueId,
        ],
      );
      final claimed = await tx.getOptional(
        'SELECT * FROM offline_outbox WHERE queue_id = ?',
        [queueId],
      );
      return claimed == null ? null : _outboxRow(claimed);
    });
  }

  Future<OutboxSummary> summary({String? scope}) async {
    await _ready;
    final rows = await _database.getAll('''
      SELECT state, COUNT(*) AS count
      FROM offline_outbox
      ${scope == null ? '' : 'WHERE scope = ?'}
      GROUP BY state
      ''', scope == null ? const [] : [scope]);
    var pending = 0;
    var retrying = 0;
    var blocked = 0;
    for (final row in rows) {
      final count = (row['count'] as num?)?.toInt() ?? 0;
      switch ('${row['state']}') {
        case 'retry':
          retrying += count;
        case 'blocked':
          blocked += count;
        default:
          pending += count;
      }
    }
    return OutboxSummary(
      pending: pending,
      retrying: retrying,
      blocked: blocked,
    );
  }

  Future<void> enqueue(Map<String, dynamic> request) async {
    await _ready;
    final queueId = '${request['queue_id']}';
    final scope = '${request['scope'] ?? ''}';
    final method = '${request['method']}';
    final path = '${request['path']}';
    final queryJson = _encodeNullable(request['query']);
    final bodyJson = _encodeNullable(request['body']);
    await _database.writeTransaction((tx) async {
      final existing = await tx.getOptional(
        '''
        SELECT scope, method, path, query_json, body_json
        FROM offline_outbox WHERE queue_id = ?
        ''',
        [queueId],
      );
      if (existing != null) {
        final sameRequest =
            '${existing['scope']}' == scope &&
            '${existing['method']}' == method &&
            '${existing['path']}' == path &&
            existing['query_json'] == queryJson &&
            existing['body_json'] == bodyJson;
        if (!sameRequest) {
          throw StateError(
            'A chave $queueId já identifica outra operação offline.',
          );
        }
        return;
      }
      await tx.execute(
        '''
        INSERT INTO offline_outbox(
          queue_id, scope, method, path, query_json, body_json, temporary_id,
          idempotency_key, created_at, state, attempt_count, next_attempt_at,
          last_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        [
          queueId,
          scope,
          method,
          path,
          queryJson,
          bodyJson,
          request['temporary_id']?.toString(),
          '${request['idempotency_key'] ?? queueId}',
          '${request['created_at'] ?? DateTime.now().toUtc().toIso8601String()}',
          '${request['state'] ?? 'pending'}',
          (request['attempt_count'] as num?)?.toInt() ?? 0,
          request['next_attempt_at']?.toString(),
          request['last_error']?.toString(),
        ],
      );
    });
  }

  Future<void> remove(String queueId) async {
    await _ready;
    await _database.execute('DELETE FROM offline_outbox WHERE queue_id = ?', [
      queueId,
    ]);
  }

  Future<void> markRetry(
    String queueId, {
    required int attemptCount,
    required DateTime nextAttemptAt,
    required String error,
  }) async {
    await _ready;
    await _database.execute(
      '''
      UPDATE offline_outbox
      SET state = 'retry',
          attempt_count = ?,
          next_attempt_at = ?,
          last_error = ?,
          lease_owner = NULL,
          lease_until = NULL
      WHERE queue_id = ?
      ''',
      [attemptCount, nextAttemptAt.toUtc().toIso8601String(), error, queueId],
    );
  }

  Future<void> markBlocked(String queueId, {required String error}) async {
    await _ready;
    await _database.execute(
      '''
      UPDATE offline_outbox
      SET state = 'blocked',
          next_attempt_at = NULL,
          last_error = ?,
          lease_owner = NULL,
          lease_until = NULL
      WHERE queue_id = ?
      ''',
      [error, queueId],
    );
  }

  /// Devolve uma operação bloqueada para a fila normal.
  ///
  /// Usado pela tela de revisão depois que o operador corrigiu a causa (uma
  /// comanda inexistente, um caixa fechado). A operação volta com a mesma
  /// chave de idempotência: se o servidor já a tiver aceitado antes de
  /// recusar, o reenvio não cria uma segunda venda.
  Future<void> unblock(String queueId) async {
    await _ready;
    await _database.execute(
      '''
      UPDATE offline_outbox
      SET state = 'pending',
          attempt_count = 0,
          next_attempt_at = NULL,
          last_error = NULL,
          lease_owner = NULL,
          lease_until = NULL
      WHERE queue_id = ? AND state = 'blocked'
      ''',
      [queueId],
    );
  }

  /// Descarta definitivamente uma operação bloqueada.
  ///
  /// Só remove itens em `blocked`: uma operação ainda elegível pode estar
  /// sendo enviada neste instante, e apagá-la perderia a venda em silêncio.
  Future<bool> discardBlocked(String queueId) async {
    await _ready;
    return _database.writeTransaction((tx) async {
      final row = await tx.getOptional(
        'SELECT state FROM offline_outbox WHERE queue_id = ?',
        [queueId],
      );
      if (row == null || '${row['state']}' != 'blocked') return false;
      await tx.execute(
        "DELETE FROM offline_outbox WHERE queue_id = ? AND state = 'blocked'",
        [queueId],
      );
      return true;
    });
  }

  Future<void> retryNow({required String scope}) async {
    await _ready;
    await _database.execute(
      '''
      UPDATE offline_outbox
      SET state = 'pending',
          next_attempt_at = NULL,
          lease_owner = NULL,
          lease_until = NULL
      WHERE scope = ? AND state = 'retry'
      ''',
      [scope],
    );
  }

  Future<void> replaceTemporaryId(
    String temporaryId,
    String realId, {
    String scope = '',
  }) async {
    await _ready;
    if (temporaryId.isEmpty || realId.isEmpty) return;
    await _database.writeTransaction((tx) async {
      await tx.execute(
        '''
        INSERT INTO offline_id_map(scope, local_id, remote_id, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(scope, local_id) DO UPDATE SET remote_id = excluded.remote_id
        ''',
        [scope, temporaryId, realId, DateTime.now().toUtc().toIso8601String()],
      );
      await tx.execute(
        'UPDATE offline_cache SET payload = replace(payload, ?, ?)',
        [temporaryId, realId],
      );
      await tx.execute(
        '''
        UPDATE offline_outbox SET
          path = replace(path, ?, ?),
          query_json = replace(query_json, ?, ?),
          body_json = replace(body_json, ?, ?),
          temporary_id = CASE
            WHEN temporary_id = ? THEN NULL ELSE temporary_id END
        WHERE scope = ?
        ''',
        [
          temporaryId,
          realId,
          temporaryId,
          realId,
          temporaryId,
          realId,
          temporaryId,
          scope,
        ],
      );
    });
  }

  Future<Map<String, dynamic>> resolveReferences(
    Map<String, dynamic> item, {
    required String scope,
  }) async {
    await _ready;
    final rows = await _database.getAll(
      'SELECT local_id, remote_id FROM offline_id_map WHERE scope = ?',
      [scope],
    );
    var encoded = jsonEncode(item);
    for (final row in rows) {
      encoded = encoded.replaceAll('${row['local_id']}', '${row['remote_id']}');
    }
    return Map<String, dynamic>.from(jsonDecode(encoded) as Map);
  }

  Future<void> applyOptimistic({
    required String path,
    required String method,
    required Map<String, dynamic> value,
    String? cacheScope,
  }) async {
    await _ready;
    final rows = await _database.getAll('''
      SELECT cache_key, payload FROM offline_cache
      ${cacheScope == null ? '' : 'WHERE cache_key LIKE ?'}
      ''', cacheScope == null ? const [] : ['$cacheScope|%']);
    final cleanPath = path.split('?').first;
    final segments = cleanPath
        .split('/')
        .where((part) => part.isNotEmpty)
        .toList();
    final entityId = method == 'POST'
        ? '${value['id'] ?? ''}'
        : (segments.isEmpty ? '' : segments.last);
    final updates = <List<Object?>>[];

    for (final row in rows) {
      final response = _decodeMap(row['payload']);
      if (response == null || response['results'] is! List) continue;
      final list = (response['results'] as List)
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
      final index = list.indexWhere((item) => '${item['id']}' == entityId);
      var changed = false;
      if (method == 'DELETE' && index >= 0) {
        list.removeAt(index);
        changed = true;
      } else if (method == 'PATCH' && index >= 0) {
        list[index] = {...list[index], ...value};
        changed = true;
      } else if (method == 'POST' &&
          '${row['cache_key']}'.contains(cleanPath) &&
          value['id'] != null) {
        list.insert(0, value);
        changed = true;
      }
      if (!changed) continue;
      response['results'] = list;
      updates.add([
        jsonEncode(response),
        DateTime.now().millisecondsSinceEpoch,
        row['cache_key'],
      ]);
    }
    if (updates.isNotEmpty) {
      await _database.executeBatch('''
        UPDATE offline_cache
        SET payload = ?, updated_at = ?
        WHERE cache_key = ?
        ''', updates);
    }
  }

  Future<void> _importLegacyJsonOnce() async {
    final legacy = _legacyFile;
    if (legacy == null || !await legacy.exists()) return;
    final imported = await _database.getOptional(
      "SELECT meta_value FROM offline_meta WHERE meta_key = 'legacy_imported'",
    );
    if (imported != null) return;

    Map<String, dynamic>? decoded;
    try {
      final value = jsonDecode(await legacy.readAsString());
      if (value is Map) decoded = Map<String, dynamic>.from(value);
    } catch (_) {
      // Keep the legacy file untouched. A corrupt legacy cache must not prevent
      // the new database from starting.
    }
    await _database.writeTransaction((tx) async {
      if (decoded != null) {
        final cache = Map<String, dynamic>.from(
          decoded['cache'] as Map? ?? const {},
        );
        if (cache.isNotEmpty) {
          await tx.executeBatch(
            '''
            INSERT INTO offline_cache(cache_key, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO NOTHING
            ''',
            cache.entries
                .map(
                  (entry) => <Object?>[
                    entry.key,
                    jsonEncode(entry.value),
                    DateTime.now().millisecondsSinceEpoch,
                  ],
                )
                .toList(),
          );
        }
        final outbox = (decoded['outbox'] as List? ?? const [])
            .whereType<Map>();
        for (final raw in outbox) {
          final item = Map<String, dynamic>.from(raw);
          final queueId = '${item['queue_id']}';
          if (queueId.isEmpty) continue;
          await tx.execute(
            '''
            INSERT INTO offline_outbox(
              queue_id, scope, method, path, query_json, body_json,
              temporary_id, idempotency_key, created_at, state,
              attempt_count, last_error
            ) VALUES (?, 'legacy', ?, ?, ?, ?, ?, ?, ?, 'blocked', 0, ?)
            ON CONFLICT(queue_id) DO NOTHING
            ''',
            [
              queueId,
              '${item['method']}',
              '${item['path']}',
              _encodeNullable(item['query']),
              _encodeNullable(item['body']),
              item['temporary_id']?.toString(),
              queueId,
              '${item['created_at'] ?? DateTime.now().toUtc().toIso8601String()}',
              'Operação importada do armazenamento legado. Revise a conta e o servidor antes de reenviar.',
            ],
          );
        }
      }
      await tx.execute(
        '''
        INSERT INTO offline_meta(meta_key, meta_value)
        VALUES ('legacy_imported', ?)
        ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
        ''',
        [DateTime.now().toUtc().toIso8601String()],
      );
    });
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    await _ready;
    await _database.close();
  }

  static Map<String, dynamic>? _decodeMap(Object? raw) {
    if (raw is! String || raw.isEmpty) return null;
    final decoded = jsonDecode(raw);
    return decoded is Map ? Map<String, dynamic>.from(decoded) : null;
  }

  static String? _encodeNullable(Object? value) =>
      value == null ? null : jsonEncode(value);

  static Map<String, dynamic> _outboxRow(dynamic row) => {
    'queue_id': '${row['queue_id']}',
    'scope': '${row['scope']}',
    'method': '${row['method']}',
    'path': '${row['path']}',
    'query': _decodeMap(row['query_json']),
    'body': _decodeMap(row['body_json']),
    'temporary_id': row['temporary_id'],
    'idempotency_key': '${row['idempotency_key']}',
    'created_at': '${row['created_at']}',
    'state': '${row['state']}',
    'attempt_count': (row['attempt_count'] as num?)?.toInt() ?? 0,
    'next_attempt_at': row['next_attempt_at'],
    'last_error': row['last_error'],
    'lease_owner': row['lease_owner'],
    'lease_until': row['lease_until'],
  };
}

class OutboxSummary {
  const OutboxSummary({
    required this.pending,
    required this.retrying,
    required this.blocked,
  });

  final int pending;
  final int retrying;
  final int blocked;

  int get total => pending + retrying + blocked;
}
