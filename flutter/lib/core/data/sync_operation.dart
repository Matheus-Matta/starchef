import 'dart:convert';

/// Tipo de alteração registrada na fila (§5).
enum SyncOperation {
  create,
  update,
  delete;

  String get code => name.toUpperCase();

  static SyncOperation parse(Object? raw) => switch ('$raw'.toUpperCase()) {
    'UPDATE' => SyncOperation.update,
    'DELETE' => SyncOperation.delete,
    _ => SyncOperation.create,
  };

  /// Deriva a operação a partir do método HTTP que a tela pediu.
  static SyncOperation fromMethod(String method) => switch (method.toUpperCase()) {
    'DELETE' => SyncOperation.delete,
    'PATCH' || 'PUT' => SyncOperation.update,
    _ => SyncOperation.create,
  };
}

/// Situação de uma operação na fila (§5).
enum SyncQueueStatus {
  pending,
  processing,
  synced,
  failed;

  String get code => name.toUpperCase();

  static SyncQueueStatus parse(Object? raw) => switch ('$raw'.toUpperCase()) {
    'PROCESSING' => SyncQueueStatus.processing,
    'SYNCED' => SyncQueueStatus.synced,
    'FAILED' => SyncQueueStatus.failed,
    _ => SyncQueueStatus.pending,
  };
}

/// Uma operação aguardando entrega ao backend.
class SyncQueueEntry {
  const SyncQueueEntry({
    required this.id,
    required this.operationId,
    required this.entityType,
    required this.entityId,
    required this.operation,
    required this.method,
    required this.path,
    required this.status,
    required this.attempts,
    required this.createdAt,
    this.query,
    this.payload,
    this.nextRetryAt,
    this.lastError,
  });

  /// Sequência FIFO (§6). Determinística mesmo para operações criadas no
  /// mesmo milissegundo.
  final int id;

  /// Chave de idempotência enviada ao backend (§7). É um UUID gerado antes de
  /// a operação existir no servidor, então um reenvio por timeout devolve a
  /// resposta original em vez de criar uma segunda venda.
  final String operationId;

  final String entityType;
  final String entityId;
  final SyncOperation operation;
  final String method;
  final String path;
  final Map<String, dynamic>? query;
  final Map<String, dynamic>? payload;
  final SyncQueueStatus status;
  final int attempts;
  final DateTime createdAt;
  final DateTime? nextRetryAt;
  final String? lastError;

  /// Resumo legível para a tela de revisão da fila.
  String get summary => '$method $path';

  static SyncQueueEntry fromRow(Map<String, Object?> row) => SyncQueueEntry(
    id: (row['id'] as num?)?.toInt() ?? 0,
    operationId: '${row['operation_id']}',
    entityType: '${row['entity_type']}',
    entityId: '${row['entity_id']}',
    operation: SyncOperation.parse(row['operation']),
    method: '${row['method']}',
    path: '${row['path']}',
    query: _decode(row['query_json']),
    payload: _decode(row['payload']),
    status: SyncQueueStatus.parse(row['status']),
    attempts: (row['attempts'] as num?)?.toInt() ?? 0,
    createdAt:
        DateTime.tryParse('${row['created_at']}')?.toUtc() ??
        DateTime.now().toUtc(),
    nextRetryAt: DateTime.tryParse('${row['next_retry_at'] ?? ''}')?.toUtc(),
    lastError: row['last_error'] as String?,
  );

  static Map<String, dynamic>? _decode(Object? raw) {
    if (raw is! String || raw.isEmpty) return null;
    final decoded = jsonDecode(raw);
    return decoded is Map ? Map<String, dynamic>.from(decoded) : null;
  }
}

/// Contagem por situação, para a barra de status e a tela de revisão.
class SyncQueueSummary {
  const SyncQueueSummary({
    this.pending = 0,
    this.processing = 0,
    this.failed = 0,
  });

  final int pending;
  final int processing;
  final int failed;

  int get total => pending + processing + failed;
  bool get hasWork => pending > 0 || processing > 0;

  @override
  bool operator ==(Object other) =>
      other is SyncQueueSummary &&
      pending == other.pending &&
      processing == other.processing &&
      failed == other.failed;

  @override
  int get hashCode => Object.hash(pending, processing, failed);
}
