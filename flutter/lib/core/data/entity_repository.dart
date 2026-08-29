import 'dart:convert';

import 'package:sqlite_async/sqlite_async.dart';

import '../logging/app_logger.dart';
import '../network/relay_origin.dart';
import 'conflict_resolver.dart';
import 'entity_catalog.dart';
import 'entity_record.dart';
import 'local_id.dart';
import 'payload_cipher.dart';
import 'pdv_database.dart';
import 'sync_operation.dart';
import 'sync_queue_service.dart';

/// Acesso a UM tipo de entidade no banco local (§27).
///
/// Toda tela fala com um repositório; nenhuma monta SQL nem chama a API
/// diretamente. É o que permite trocar a implementação — hoje SQLite, amanhã
/// outra coisa — sem tocar em uma única tela.
///
/// A regra que dá nome à arquitetura mora aqui: [saveLocal] grava a entidade
/// **e** a operação de sincronização na mesma transação (§5). Ou as duas
/// existem, ou nenhuma existe. Nunca uma venda salva sem ninguém para
/// entregá-la ao servidor.
class EntityRepository {
  EntityRepository({
    required this.database,
    required this.descriptor,
    required this.scope,
    PayloadCipher? cipher,
  }) : _cipher = cipher ?? PayloadCipher.disabled();

  /// Teto de linhas lidas quando o filtro não pode ser resolvido em SQL.
  /// Um restaurante não tem mais catálogo do que isso em operação; o limite
  /// existe para que um filtro inesperado não carregue o banco inteiro.
  static const _scanLimit = 5000;

  /// Chaves de controle da API que nunca são filtro de conteúdo.
  static const _controlKeys = {
    'page',
    'page_size',
    'limit',
    'offset',
    'ordering',
    'search',
    'format',
    'updated_after',
    'include_deleted',
  };

  final PdvDatabase database;
  final EntityDescriptor descriptor;
  final String scope;
  final PayloadCipher _cipher;

  String get type => descriptor.type;

  // ---------------------------------------------------------------- leitura

  Future<EntityRecord?> read(String id, {bool includeDeleted = false}) async {
    final row = await database.querySingle(
      '''
      SELECT * FROM entities
      WHERE scope = ? AND entity_type = ? AND entity_id = ?
      ${includeDeleted ? '' : 'AND deleted_at IS NULL'}
      ''',
      [scope, type, id],
    );
    if (row == null) return null;
    return EntityRecord.fromRow(
      row,
      decodedPayload: await _cipher.decrypt('${row['payload']}'),
    );
  }

  /// Lista paginada, com os mesmos parâmetros que a API aceita (§13).
  ///
  /// Quando todos os filtros couberem nas colunas indexadas, a paginação é
  /// feita em SQL (`LIMIT ? OFFSET ?`) e nem os registros das outras páginas
  /// são lidos. Filtros sobre campos livres do payload caem para uma varredura
  /// limitada — correta em qualquer build do SQLite, sem depender da extensão
  /// JSON1 estar compilada.
  Future<LocalPage> list({Map<String, dynamic>? query}) async {
    final parameters = Map<String, dynamic>.from(query ?? const {});
    final page = _positiveInt(parameters['page'], fallback: 1);
    final pageSize = _positiveInt(
      parameters['page_size'] ?? parameters['limit'],
      fallback: defaultPageSize,
    );
    final includeDeleted = const {
      '1',
      'true',
      'yes',
    }.contains('${parameters['include_deleted'] ?? ''}'.toLowerCase());

    final clauses = <String>[
      'scope = ?',
      'entity_type = ?',
      if (!includeDeleted) 'deleted_at IS NULL',
    ];
    final values = <Object?>[scope, type];
    final residual = <String, dynamic>{};

    parameters.forEach((key, value) {
      if (_controlKeys.contains(key)) return;
      final column = _indexedColumnFor(key);
      if (column == null || value == null) {
        residual[key] = value;
        return;
      }
      clauses.add('$column = ?');
      values.add('$value');
    });

    final search = '${parameters['search'] ?? ''}'.trim();
    final updatedAfter = '${parameters['updated_after'] ?? ''}'.trim();
    if (updatedAfter.isNotEmpty) {
      clauses.add('updated_at > ?');
      values.add(updatedAfter);
    }

    final where = 'WHERE ${clauses.join(' AND ')}';
    final order = descriptor.ordering == EntityOrdering.recentFirst
        ? 'ORDER BY sort_key DESC, entity_id'
        : 'ORDER BY sort_key ASC, entity_id';

    if (residual.isEmpty && search.isEmpty) {
      final countRow = await database.querySingle(
        'SELECT COUNT(*) AS total FROM entities $where',
        values,
      );
      final count = (countRow?['total'] as num?)?.toInt() ?? 0;
      final rows = await database.query(
        'SELECT * FROM entities $where $order LIMIT ? OFFSET ?',
        [...values, pageSize, (page - 1) * pageSize],
      );
      return LocalPage(
        count: count,
        results: await _decodeAll(rows),
        page: page,
        pageSize: pageSize,
      );
    }

    final rows = await database.query(
      'SELECT * FROM entities $where $order LIMIT $_scanLimit',
      values,
    );
    final decoded = await _decodeAll(rows);
    // Um parâmetro que NENHUM registro deste tipo possui é ignorado, como o
    // backend faz com um filtro desconhecido. Já um campo que existe em parte
    // dos registros filtra de verdade: sem essa distinção, pedir
    // `?category=X` devolvia também os produtos sem categoria.
    final knownKeys = <String>{for (final item in decoded) ...item.keys};
    final effective = {
      for (final entry in residual.entries)
        if (knownKeys.contains(entry.key)) entry.key: entry.value,
    };
    final filtered = decoded
        .where((item) => _matchesResidual(item, effective, search))
        .toList(growable: false);
    final start = (page - 1) * pageSize;
    return LocalPage(
      count: filtered.length,
      results: start >= filtered.length
          ? const []
          : filtered.sublist(start, (start + pageSize).clamp(0, filtered.length)),
      page: page,
      pageSize: pageSize,
    );
  }

  /// Tamanho de página padrão da sincronização e das listagens locais (§13).
  static const defaultPageSize = 20;

  /// Registros alterados localmente e ainda não confirmados.
  Future<List<EntityRecord>> pendingRecords() async {
    final rows = await database.query(
      '''
      SELECT * FROM entities
      WHERE scope = ? AND entity_type = ? AND sync_status = 'pending'
      ORDER BY updated_at
      ''',
      [scope, type],
    );
    return [
      for (final row in rows)
        EntityRecord.fromRow(
          row,
          decodedPayload: await _cipher.decrypt('${row['payload']}'),
        ),
    ];
  }

  // ---------------------------------------------------------------- escrita

  /// Grava uma alteração feita neste terminal e enfileira a sincronização.
  ///
  /// Devolve o registro já persistido, para que a tela desenhe imediatamente
  /// sem esperar rede (§4, §29).
  Future<EntityWrite> saveLocal(
    Map<String, dynamic> payload, {
    required SyncOperation operation,
    required String method,
    required String path,
    Map<String, dynamic>? query,
    String? id,
    Map<String, dynamic>? requestBody,
    Future<void> Function(SqliteWriteContext tx)? guard,
  }) async {
    final entityId = id ?? '${payload['id'] ?? ''}';
    if (entityId.isEmpty) {
      throw ArgumentError('Uma entidade local precisa de identificador.');
    }
    final now = DateTime.now().toUtc();
    final merged = {...sanitize(payload), 'id': entityId};
    final encoded = await _cipher.encrypt(jsonEncode(merged));
    final operationId = LocalId.uuid();

    return database.write((tx) async {
      // Verificação e gravação na MESMA transação. É o que separa "consultei e
      // depois criei" (duas aberturas simultâneas leem "livre" antes de
      // qualquer uma gravar) de uma exclusividade de verdade: se o guard
      // lançar, nada foi escrito — nem a entidade, nem a operação da fila.
      if (guard != null) await guard(tx);
      final existing = await tx.getOptional(
        '''
        SELECT version, created_at FROM entities
        WHERE scope = ? AND entity_type = ? AND entity_id = ?
        ''',
        [scope, type, entityId],
      );
      final version = ((existing?['version'] as num?)?.toInt() ?? 0) + 1;
      final createdAt = '${existing?['created_at'] ?? now.toIso8601String()}';

      await _upsert(
        tx,
        entityId: entityId,
        payload: merged,
        encodedPayload: encoded,
        version: version,
        source: ChangeSource.local,
        syncStatus: SyncStatus.pending,
        createdAt: createdAt,
        updatedAt: now.toIso8601String(),
        deletedAt: operation == SyncOperation.delete
            ? now.toIso8601String()
            : null,
      );

      // Mesma transação da entidade: é isto que o Transactional Outbox
      // garante (§5).
      await _enqueue(
        tx,
        operationId: operationId,
        entityId: entityId,
        operation: operation,
        method: method,
        path: path,
        query: query,
        payload: requestBody ?? payload,
        createdAt: now,
      );

      return EntityWrite(
        record: EntityRecord(
          type: type,
          id: entityId,
          payload: merged,
          version: version,
          source: ChangeSource.local,
          syncStatus: SyncStatus.pending,
          createdAt: DateTime.tryParse(createdAt)?.toUtc() ?? now,
          updatedAt: now,
          deletedAt: operation == SyncOperation.delete ? now : null,
        ),
        operationId: operationId,
      );
    });
  }

  /// Aplica uma alteração vinda do servidor ou do WebSocket (§11, §12).
  ///
  /// Não gera operação de saída: seria exatamente o laço descrito em §12.
  Future<EntityRecord?> applyRemote(
    Map<String, dynamic> payload, {
    bool overwriteLocalChanges = false,
    String? ignoreQueuedOperationId,
  }) async {
    final entityId = '${payload['id'] ?? ''}';
    if (entityId.isEmpty) return null;
    final now = DateTime.now().toUtc();
    final serverVersion = '${payload['updated_at'] ?? ''}';
    final clean = sanitize(payload);
    final encoded = await _cipher.encrypt(jsonEncode(clean));

    final stored = await read(entityId, includeDeleted: true);
    // Evento fora de ordem: com WebSocket e sincronização periódica correndo
    // juntos, a mesma entidade chega duas vezes e a segunda pode ser a mais
    // antiga. Aplicá-la desfaria uma atualização já recebida.
    if (!overwriteLocalChanges &&
        ConflictResolver.isStale(local: stored, remote: payload)) {
      return null;
    }
    if (ConflictResolver.resolve(
          local: stored,
          remote: payload,
          confirmedByDelivery: overwriteLocalChanges,
        ) ==
        ConflictOutcome.keepLocal) {
      return null;
    }

    return database.write((tx) async {
      final existing = await tx.getOptional(
        '''
        SELECT version, created_at, sync_status FROM entities
        WHERE scope = ? AND entity_type = ? AND entity_id = ?
        ''',
        [scope, type, entityId],
      );
      // A entidade só volta a ser "sincronizada" quando não sobrou nada dela
      // na fila. Confirmar a entrega de UMA operação não significa que as
      // outras já subiram — e marcar sincronizado cedo demais autorizaria a
      // próxima leitura do servidor a apagar o que ainda está esperando.
      // A operação que está sendo confirmada AGORA não conta: ela só sai da
      // fila depois desta gravação, e considerá-la deixaria toda entrega
      // bem-sucedida marcando a entidade como ainda pendente.
      final stillQueued = await tx.getOptional(
        '''
        SELECT 1 FROM sync_queue
        WHERE scope = ? AND entity_type = ? AND entity_id = ?
          AND operation_id IS NOT ?
        ''',
        [scope, type, entityId, ignoreQueuedOperationId],
      );
      final syncStatus = stillQueued == null
          ? SyncStatus.synced
          : SyncStatus.pending;
      final version = ((existing?['version'] as num?)?.toInt() ?? 0) + 1;
      final createdAt = '${existing?['created_at'] ?? now.toIso8601String()}';
      await _upsert(
        tx,
        entityId: entityId,
        payload: clean,
        encodedPayload: encoded,
        version: version,
        source: ChangeSource.remote,
        syncStatus: syncStatus,
        createdAt: createdAt,
        updatedAt: now.toIso8601String(),
        serverVersion: serverVersion.isEmpty ? null : serverVersion,
        deletedAt: payload['deleted_at']?.toString(),
      );
      return EntityRecord(
        type: type,
        id: entityId,
        payload: clean,
        version: version,
        serverVersion: serverVersion.isEmpty ? null : serverVersion,
        source: ChangeSource.remote,
        syncStatus: syncStatus,
        createdAt: DateTime.tryParse(createdAt)?.toUtc() ?? now,
        updatedAt: now,
        deletedAt: DateTime.tryParse('${payload['deleted_at'] ?? ''}')?.toUtc(),
      );
    });
  }

  /// Aplica uma lista vinda de uma página da API.
  Future<int> applyRemoteList(List<Map<String, dynamic>> payloads) async {
    var applied = 0;
    for (final payload in payloads) {
      if (await applyRemote(payload) != null) applied += 1;
    }
    return applied;
  }

  /// Marca como excluído sem apagar (§22).
  Future<void> markRemoteDeleted(String id) async {
    await database.execute(
      '''
      UPDATE entities
      SET deleted_at = ?, source = 'REMOTE', sync_status = 'synced',
          updated_at = ?
      WHERE scope = ? AND entity_type = ? AND entity_id = ?
        AND sync_status != 'pending'
      ''',
      [
        DateTime.now().toUtc().toIso8601String(),
        DateTime.now().toUtc().toIso8601String(),
        scope,
        type,
        id,
      ],
    );
  }

  /// Confirma que a alteração local foi aceita pelo servidor.
  ///
  /// O `serverPayload` só substitui o registro quando ele **é** o registro:
  /// a resposta de `POST /orders/<id>/items/` é o ITEM criado, não o pedido, e
  /// aplicá-la aqui gravaria um pedido com o identificador do item.
  Future<void> markSynced(
    String id, {
    Map<String, dynamic>? serverPayload,
    String? ignoreQueuedOperationId,
  }) async {
    if (serverPayload != null && '${serverPayload['id'] ?? ''}' == id) {
      await applyRemote(
        serverPayload,
        overwriteLocalChanges: true,
        ignoreQueuedOperationId: ignoreQueuedOperationId,
      );
      return;
    }
    // `AND NOT EXISTS (...)`: uma entidade com outras operações ainda na fila
    // continua pendente. Sem isso, entregar o primeiro de dois itens marcava o
    // pedido inteiro como sincronizado, e a próxima leitura vinda do servidor
    // sobrescrevia o segundo item — que sumia da tela até a fila esvaziar.
    await database.execute(
      '''
      UPDATE entities SET sync_status = 'synced'
      WHERE scope = ? AND entity_type = ? AND entity_id = ?
        AND NOT EXISTS (
          SELECT 1 FROM sync_queue
          WHERE sync_queue.scope = entities.scope
            AND sync_queue.entity_type = entities.entity_type
            AND sync_queue.entity_id = entities.entity_id
            AND sync_queue.operation_id IS NOT ?
        )
      ''',
      [scope, type, id, ignoreQueuedOperationId],
    );
  }

  /// Ainda há operação na fila para esta entidade?
  Future<bool> hasQueuedOperations(String entityId) async {
    final row = await database.querySingle(
      '''
      SELECT 1 FROM sync_queue
      WHERE scope = ? AND entity_type = ? AND entity_id = ?
      ''',
      [scope, type, entityId],
    );
    return row != null;
  }

  /// O servidor recusou definitivamente. O registro permanece visível para
  /// que o operador saiba o que precisa corrigir.
  Future<void> markFailed(String id) async {
    await database.execute(
      '''
      UPDATE entities SET sync_status = 'failed'
      WHERE scope = ? AND entity_type = ? AND entity_id = ?
      ''',
      [scope, type, id],
    );
  }

  /// Reescreve, dentro do payload da entidade, uma referência que virou real.
  ///
  /// Serve aos sub-recursos criados junto do pai — item, pagamento,
  /// movimentação de caixa. Sem isso o item continuaria com o identificador
  /// local depois de confirmado, e a próxima leitura vinda do servidor o
  /// trataria como "ainda pendente" e o somaria de novo: o mesmo item duas
  /// vezes na conta.
  Future<void> replaceReference(
    String entityId,
    String localId,
    String remoteId,
  ) async {
    if (localId.isEmpty || remoteId.isEmpty || localId == remoteId) return;
    final record = await read(entityId, includeDeleted: true);
    if (record == null) return;
    final rewritten = jsonDecode(
      jsonEncode(record.payload).replaceAll(localId, remoteId),
    );
    if (rewritten is! Map) return;
    final payload = Map<String, dynamic>.from(rewritten);
    final encoded = await _cipher.encrypt(jsonEncode(payload));
    await database.write(
      (tx) => _upsert(
        tx,
        entityId: entityId,
        payload: payload,
        encodedPayload: encoded,
        version: record.version,
        source: record.source,
        syncStatus: record.syncStatus,
        createdAt: record.createdAt.toIso8601String(),
        updatedAt: DateTime.now().toUtc().toIso8601String(),
        deletedAt: record.deletedAt?.toIso8601String(),
      ),
    );
  }

  /// Troca o ID temporário pelo definitivo depois que a criação subiu.
  Future<void> replaceId(String temporaryId, String realId) async {
    if (temporaryId.isEmpty || realId.isEmpty || temporaryId == realId) return;
    final record = await read(temporaryId, includeDeleted: true);
    if (record == null) return;
    final payload = {...record.payload, 'id': realId};
    final encoded = await _cipher.encrypt(jsonEncode(payload));
    await database.write((tx) async {
      await tx.execute(
        'DELETE FROM entities WHERE scope = ? AND entity_type = ? AND entity_id = ?',
        [scope, type, temporaryId],
      );
      await _upsert(
        tx,
        entityId: realId,
        payload: payload,
        encodedPayload: encoded,
        version: record.version,
        source: record.source,
        syncStatus: record.syncStatus,
        createdAt: record.createdAt.toIso8601String(),
        updatedAt: DateTime.now().toUtc().toIso8601String(),
        deletedAt: record.deletedAt?.toIso8601String(),
      );
      await tx.execute(
        '''
        INSERT INTO id_map(scope, local_id, remote_id, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(scope, local_id) DO UPDATE SET remote_id = excluded.remote_id
        ''',
        [
          scope,
          temporaryId,
          realId,
          DateTime.now().toUtc().toIso8601String(),
        ],
      );
    });
  }

  // ------------------------------------------------------------- internals

  /// Reescreve as entradas de código desta entidade.
  ///
  /// Vive dentro do `_upsert` de propósito: entidade e índice mudam na mesma
  /// transação. Um índice atualizado depois ficaria momentaneamente apontando
  /// para um preço, um nome ou um código que já não valem — e é justamente
  /// nesse instante que alguém bipa o produto.
  Future<void> _syncCodeIndex(
    SqliteWriteContext tx, {
    required String entityId,
    required Map<String, dynamic> payload,
    required bool deleted,
  }) async {
    if (descriptor.codeFields.isEmpty) return;
    await tx.execute(
      'DELETE FROM entity_codes WHERE scope = ? AND entity_type = ? '
      'AND entity_id = ?',
      [scope, type, entityId],
    );
    if (deleted) return;
    for (final field in descriptor.codeFields) {
      final code = normalizeCode(payload[field]);
      if (code.isEmpty) continue;
      await tx.execute(
        'INSERT OR REPLACE INTO entity_codes(scope, entity_type, field, code, '
        'entity_id) VALUES (?, ?, ?, ?, ?)',
        [scope, type, field, code, entityId],
      );
    }
  }

  /// Como um código é comparado: sem espaços e sem diferença de caixa.
  ///
  /// Zeros à esquerda são preservados — `0000012345670` e `12345670` são
  /// códigos diferentes, e apagá-los faria o leitor não achar o produto.
  static String normalizeCode(Object? value) =>
      '${value ?? ''}'.trim().toUpperCase();

  /// A entidade cujo código bate com [code], na ordem de [codeFields].
  ///
  /// Devolve também QUAL campo casou: a tela de venda precisa saber se foi o
  /// código de barras ou o código interno para explicar o que aconteceu.
  Future<CodeMatch?> findByCode(String code) async {
    final normalized = normalizeCode(code);
    if (normalized.isEmpty || descriptor.codeFields.isEmpty) return null;

    var rows = await database.query(
      'SELECT field, entity_id FROM entity_codes '
      'WHERE scope = ? AND entity_type = ? AND code = ?',
      [scope, type, normalized],
    );
    if (rows.isEmpty && await _codeIndexIsCold()) {
      // Base que já existia antes do índice: reconstrói uma vez e repete a
      // consulta, em vez de varrer o catálogo a cada leitura para sempre.
      await rebuildCodeIndex();
      rows = await database.query(
        'SELECT field, entity_id FROM entity_codes '
        'WHERE scope = ? AND entity_type = ? AND code = ?',
        [scope, type, normalized],
      );
    }
    if (rows.isEmpty) return null;

    for (final field in descriptor.codeFields) {
      for (final row in rows) {
        if ('${row['field']}' != field) continue;
        final record = await read('${row['entity_id']}');
        if (record != null) return CodeMatch(record: record, field: field);
      }
    }
    return null;
  }

  Future<bool> _codeIndexIsCold() async {
    final row = await database.querySingle(
      'SELECT COUNT(*) AS total FROM entity_codes '
      'WHERE scope = ? AND entity_type = ?',
      [scope, type],
    );
    return ((row?['total'] as num?)?.toInt() ?? 0) == 0;
  }

  /// Recria o índice a partir do que já está gravado.
  Future<void> rebuildCodeIndex() async {
    if (descriptor.codeFields.isEmpty) return;
    final rows = await database.query(
      'SELECT entity_id, payload FROM entities '
      'WHERE scope = ? AND entity_type = ? AND deleted_at IS NULL',
      [scope, type],
    );
    final decoded = <String, Map<String, dynamic>>{};
    for (final row in rows) {
      final payload = await _cipher.decrypt('${row['payload']}');
      final map = jsonDecode(payload);
      if (map is Map) {
        decoded['${row['entity_id']}'] = Map<String, dynamic>.from(map);
      }
    }
    await database.write((tx) async {
      await tx.execute(
        'DELETE FROM entity_codes WHERE scope = ? AND entity_type = ?',
        [scope, type],
      );
      for (final entry in decoded.entries) {
        await _syncCodeIndex(
          tx,
          entityId: entry.key,
          payload: entry.value,
          deleted: false,
        );
      }
    });
  }

  Future<void> _upsert(
    SqliteWriteContext tx, {
    required String entityId,
    required Map<String, dynamic> payload,
    required String encodedPayload,
    required int version,
    required ChangeSource source,
    required SyncStatus syncStatus,
    required String createdAt,
    required String updatedAt,
    String? serverVersion,
    String? deletedAt,
  }) async {
    await tx.execute(
      '''
      INSERT INTO entities(
        scope, entity_type, entity_id, parent_id, restaurant_id, status,
        payload, version, server_version, source, sync_status,
        created_at, updated_at, sort_key, deleted_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(scope, entity_type, entity_id) DO UPDATE SET
        parent_id = excluded.parent_id,
        restaurant_id = excluded.restaurant_id,
        status = excluded.status,
        payload = excluded.payload,
        version = excluded.version,
        server_version = COALESCE(excluded.server_version, entities.server_version),
        source = excluded.source,
        sync_status = excluded.sync_status,
        updated_at = excluded.updated_at,
        sort_key = excluded.sort_key,
        deleted_at = excluded.deleted_at
      ''',
      [
        scope,
        type,
        entityId,
        _fieldOf(payload, descriptor.parentField),
        _fieldOf(payload, descriptor.restaurantField),
        _fieldOf(payload, descriptor.statusField),
        encodedPayload,
        version,
        serverVersion,
        source.code,
        syncStatus.code,
        createdAt,
        updatedAt,
        sortKeyFor(payload, descriptor),
        deletedAt,
      ],
    );
    await _syncCodeIndex(
      tx,
      entityId: entityId,
      payload: payload,
      deleted: deletedAt != null,
    );
  }

  Future<void> _enqueue(
    SqliteWriteContext tx, {
    required String operationId,
    required String entityId,
    required SyncOperation operation,
    required String method,
    required String path,
    required Map<String, dynamic>? query,
    required Map<String, dynamic>? payload,
    required DateTime createdAt,
  }) async {
    await tx.execute(
      '''
      INSERT INTO sync_queue(
        operation_id, scope, entity_type, entity_id, operation, method, path,
        query_json, payload, status, attempts, created_at, updated_at, origin_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0, ?, ?, ?)
      ''',
      [
        operationId,
        scope,
        type,
        entityId,
        operation.code,
        method,
        path,
        query == null ? null : jsonEncode(query),
        payload == null ? null : jsonEncode(payload),
        createdAt.toIso8601String(),
        createdAt.toIso8601String(),
        // Quando esta gravação é o Caixa Principal executando por um
        // secundário, a operação sobe com as credenciais DELE — não com as do
        // principal. `RelayOrigin.current` é `null` no caminho comum.
        SyncQueueService.encodeOrigin(RelayOrigin.current),
      ],
    );
  }

  Future<List<Map<String, dynamic>>> _decodeAll(
    List<Map<String, Object?>> rows,
  ) async {
    final results = <Map<String, dynamic>>[];
    for (final row in rows) {
      try {
        final record = EntityRecord.fromRow(
          row,
          decodedPayload: await _cipher.decrypt('${row['payload']}'),
        );
        results.add(record.toApiJson());
      } on FormatException catch (error) {
        // Um registro ilegível (chave do cofre perdida ao migrar de máquina,
        // linha corrompida) não pode derrubar a tela inteira: no Linux, o
        // Secret Service pode devolver outra chave depois de uma reinstalação
        // e isso apagaria o cardápio da tela sem explicação. O registro é
        // pulado e volta na próxima sincronização.
        AppLogger.instance.warning(
          'registro_local_ilegivel',
          data: {
            'entity_type': '${row['entity_type']}',
            'entity_id': '${row['entity_id']}',
            'causa': error.message,
          },
        );
      }
    }
    return results;
  }

  String? _indexedColumnFor(String key) => switch (key) {
    'id' => 'entity_id',
    _ when key == descriptor.restaurantField => 'restaurant_id',
    _ when key == descriptor.parentField => 'parent_id',
    _ when key == descriptor.statusField => 'status',
    _ => null,
  };

  static bool _matchesResidual(
    Map<String, dynamic> item,
    Map<String, dynamic> filters,
    String search,
  ) {
    for (final entry in filters.entries) {
      if (!_looselyEqual(item[entry.key], entry.value)) return false;
    }
    if (search.isEmpty) return true;
    return jsonEncode(item).toLowerCase().contains(search.toLowerCase());
  }

  static bool _looselyEqual(Object? actual, Object? expected) {
    final left = '$actual'.toLowerCase();
    final right = '$expected'.toLowerCase();
    if (left == right) return true;
    // `true`/`True`/`1` chegam misturados entre query string e JSON.
    const truthy = {'true', '1'};
    const falsy = {'false', '0'};
    if (truthy.contains(left) && truthy.contains(right)) return true;
    if (falsy.contains(left) && falsy.contains(right)) return true;
    return false;
  }

  /// Metadados de transporte nunca entram no registro persistido.
  ///
  /// `_offline_pending`, `_local`, `_relayed_to_principal` e afins descrevem
  /// COMO um dado chegou, não o dado. Gravá-los deixaria um pedido marcado
  /// como pendente para sempre, mesmo depois de sincronizado — foi assim que
  /// a etiqueta "salvo localmente" ficava colada no pedido.
  static Map<String, dynamic> sanitize(Map<String, dynamic> payload) => {
    for (final entry in payload.entries)
      if (!entry.key.startsWith('_')) entry.key: entry.value,
  };

  static String? _fieldOf(Map<String, dynamic> payload, String? field) {
    if (field == null) return null;
    final value = payload[field];
    if (value == null) return null;
    if (value is Map) return '${value['id'] ?? ''}';
    return '$value';
  }

  /// Chave de ordenação persistida junto do registro (§13).
  static String sortKeyFor(
    Map<String, dynamic> payload,
    EntityDescriptor descriptor,
  ) {
    if (descriptor.ordering == EntityOrdering.recentFirst) {
      // Sempre a mesma escala. Usar `sequence` quando ele existe e a data
      // quando não existe misturava dois formatos na mesma coluna: um pedido
      // do servidor virava `000000000042` e um criado offline virava
      // `2026-08-28T...`. Como a comparação é textual, TODOS os pedidos do
      // servidor caíam depois de todos os locais — a lista deixava de ser
      // "mais recente primeiro" e passava a ser "offline primeiro".
      return '${payload['created_at'] ?? payload['opened_at'] ?? payload['updated_at'] ?? DateTime.now().toUtc().toIso8601String()}';
    }
    final name = payload['name'] ?? payload['title'] ?? payload['number'];
    if (name != null) {
      final text = '$name';
      final asNumber = num.tryParse(text);
      if (asNumber != null) {
        return asNumber.toInt().toString().padLeft(12, '0');
      }
      return text.toLowerCase();
    }
    return '${payload['id'] ?? ''}';
  }

  static int _positiveInt(Object? raw, {required int fallback}) {
    final parsed = int.tryParse('${raw ?? ''}');
    if (parsed == null || parsed <= 0) return fallback;
    return parsed;
  }
}

/// Resultado de uma gravação local: o registro persistido e a operação que
/// ficou na fila para entregá-lo.
///
/// A tela precisa do primeiro para desenhar; quem corrige um corpo já
/// enfileirado (a comanda de cozinha que saiu na impressora antes de a fila
/// sincronizar) precisa do segundo.
class EntityWrite {
  const EntityWrite({required this.record, required this.operationId});

  final EntityRecord record;

  /// Chave de idempotência da operação enfileirada (§7).
  final String operationId;

  Map<String, dynamic> toApiJson() => {
    ...record.toApiJson(),
    '_sync_operation_id': operationId,
  };
}

/// O que casou com um código lido: o registro e o campo que o continha.
class CodeMatch {
  const CodeMatch({required this.record, required this.field});

  final EntityRecord record;

  /// `ean`, `internal_code`, `code`... — a tela usa para explicar a leitura.
  final String field;

  Map<String, dynamic> get payload => record.payload;
}
