import 'dart:convert';

/// Origem de uma alteração (§12).
///
/// É o que impede o laço `backend -> websocket -> sqlite -> fila -> backend`.
/// Só o que nasceu [local] entra na fila de saída; o que chegou [remote] é
/// aplicado e para por aí.
enum ChangeSource {
  local,
  remote;

  String get code => this == ChangeSource.local ? 'LOCAL' : 'REMOTE';

  static ChangeSource parse(Object? raw) =>
      '$raw' == 'REMOTE' ? ChangeSource.remote : ChangeSource.local;
}

/// Situação do registro perante o servidor (§21).
enum SyncStatus {
  /// Alterado localmente e ainda não confirmado pelo servidor.
  pending,

  /// Igual ao que o servidor conhece.
  synced,

  /// O servidor recusou a alteração; precisa de revisão humana.
  failed;

  String get code => name;

  static SyncStatus parse(Object? raw) => switch ('$raw') {
    'synced' => SyncStatus.synced,
    'failed' => SyncStatus.failed,
    _ => SyncStatus.pending,
  };
}

/// Uma entidade do restaurante guardada no SQLite local.
class EntityRecord {
  const EntityRecord({
    required this.type,
    required this.id,
    required this.payload,
    required this.version,
    required this.source,
    required this.syncStatus,
    required this.createdAt,
    required this.updatedAt,
    this.serverVersion,
    this.deletedAt,
  });

  final String type;
  final String id;
  final Map<String, dynamic> payload;

  /// Contador incrementado a cada gravação local; usado pelo
  /// [ConflictResolver] para saber se o terminal alterou o registro depois da
  /// última versão vinda do servidor.
  final int version;

  /// `updated_at` que o servidor informou na última sincronização.
  final String? serverVersion;

  final ChangeSource source;
  final SyncStatus syncStatus;
  final DateTime createdAt;
  final DateTime updatedAt;

  /// Exclusão lógica (§22): o registro continua no banco para que a exclusão
  /// possa ser avisada ao servidor quando a rede voltar.
  final DateTime? deletedAt;

  bool get isDeleted => deletedAt != null;
  bool get isPending => syncStatus == SyncStatus.pending;

  /// Payload como a API o devolveria, acrescido dos metadados que as telas já
  /// usam para desenhar o estado "pendente".
  Map<String, dynamic> toApiJson() => {
    ...payload,
    'id': id,
    if (isPending) '_offline_pending': true,
    if (syncStatus == SyncStatus.failed) '_offline_failed': true,
  };

  EntityRecord copyWith({
    Map<String, dynamic>? payload,
    int? version,
    String? serverVersion,
    ChangeSource? source,
    SyncStatus? syncStatus,
    DateTime? updatedAt,
    DateTime? deletedAt,
    bool clearDeletedAt = false,
  }) => EntityRecord(
    type: type,
    id: id,
    payload: payload ?? this.payload,
    version: version ?? this.version,
    serverVersion: serverVersion ?? this.serverVersion,
    source: source ?? this.source,
    syncStatus: syncStatus ?? this.syncStatus,
    createdAt: createdAt,
    updatedAt: updatedAt ?? this.updatedAt,
    deletedAt: clearDeletedAt ? null : (deletedAt ?? this.deletedAt),
  );

  static EntityRecord fromRow(
    Map<String, Object?> row, {
    required String decodedPayload,
  }) {
    final decoded = jsonDecode(decodedPayload);
    return EntityRecord(
      type: '${row['entity_type']}',
      id: '${row['entity_id']}',
      payload: decoded is Map
          ? Map<String, dynamic>.from(decoded)
          : <String, dynamic>{},
      version: (row['version'] as num?)?.toInt() ?? 1,
      serverVersion: row['server_version'] as String?,
      source: ChangeSource.parse(row['source']),
      syncStatus: SyncStatus.parse(row['sync_status']),
      createdAt:
          DateTime.tryParse('${row['created_at']}')?.toUtc() ??
          DateTime.now().toUtc(),
      updatedAt:
          DateTime.tryParse('${row['updated_at']}')?.toUtc() ??
          DateTime.now().toUtc(),
      deletedAt: DateTime.tryParse('${row['deleted_at'] ?? ''}')?.toUtc(),
    );
  }
}

/// Página de resultados local, no mesmo formato que o DRF devolve.
///
/// As telas já sabem ler `count`/`results`; devolver outra forma obrigaria a
/// mexer em cada lista do PDV só para trocar a origem dos dados.
class LocalPage {
  const LocalPage({
    required this.count,
    required this.results,
    required this.page,
    required this.pageSize,
  });

  final int count;
  final List<Map<String, dynamic>> results;
  final int page;
  final int pageSize;

  bool get hasNext => page * pageSize < count;
  bool get hasPrevious => page > 1;

  /// Uma página além do fim devolve lista vazia — nunca repete a anterior
  /// nem inventa registros (§13).
  Map<String, dynamic> toJson({String? basePath}) => {
    'count': count,
    'next': hasNext && basePath != null
        ? '$basePath?page=${page + 1}&page_size=$pageSize'
        : null,
    'previous': hasPrevious && basePath != null
        ? '$basePath?page=${page - 1}&page_size=$pageSize'
        : null,
    'results': results,
    '_local': true,
  };
}
