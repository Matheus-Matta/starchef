import 'dart:convert';
import 'dart:math';

import '../network/relay_origin.dart';
import 'local_id.dart';
import 'pdv_database.dart';
import 'sync_operation.dart';

/// Fila de sincronização do Caixa Principal (§5, §6, §23).
///
/// A fila é FIFO por padrão, mas FIFO cego trava a loja inteira: uma operação
/// recusada por regra de negócio (uma comanda que não existe mais no servidor)
/// seguraria todas as vendas atrás dela. Aqui a ordem é preservada **onde ela
/// importa** — quem depende de um ID que ainda não existe no servidor espera a
/// sua vez —, e o que é independente passa na frente.
class SyncQueueService {
  SyncQueueService({required this.database, String? leaseOwner})
    : _leaseOwner = leaseOwner ?? 'engine-${LocalId.uuid()}';

  /// Escada de backoff pedida em §23. O último degrau se repete.
  static const retryLadder = [
    Duration(seconds: 5),
    Duration(seconds: 15),
    Duration(seconds: 30),
    Duration(minutes: 1),
    Duration(minutes: 5),
  ];

  /// Tempo que uma operação fica reservada por um processo. O PDV, a janela
  /// da Balança Rápida e o servidor local compartilham o banco; sem reserva,
  /// dois deles enviariam a mesma operação ao mesmo tempo.
  static const leaseDuration = Duration(seconds: 30);

  /// Quantas operações a fila varre antes de desistir de achar uma elegível.
  static const _scanWindow = 200;

  /// `"client_item_id":"offline-..."` e afins.
  static final _clientIdField = RegExp(r'"client_[a-z_]*id"\s*:\s*"[^"]*"');

  final PdvDatabase database;
  final String _leaseOwner;

  String get leaseOwner => _leaseOwner;

  /// Enfileira uma operação avulsa (sem entidade local correspondente).
  ///
  /// O caminho normal é [EntityRepository.saveLocal], que grava entidade e
  /// operação na mesma transação. Este método existe para operações que não
  /// alteram uma entidade do catálogo — por exemplo, o vínculo de uma comanda
  /// com a mesa.
  Future<String> enqueue({
    required String scope,
    required String entityType,
    required String entityId,
    required SyncOperation operation,
    required String method,
    required String path,
    Map<String, dynamic>? query,
    Map<String, dynamic>? payload,
    String? operationId,
  }) async {
    final id = operationId ?? LocalId.uuid();
    final now = DateTime.now().toUtc().toIso8601String();
    await database.execute(
      '''
      INSERT INTO sync_queue(
        operation_id, scope, entity_type, entity_id, operation, method, path,
        query_json, payload, status, attempts, created_at, updated_at, origin_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0, ?, ?, ?)
      ON CONFLICT(operation_id) DO NOTHING
      ''',
      [
        id,
        scope,
        entityType,
        entityId,
        operation.code,
        method,
        path,
        query == null ? null : jsonEncode(query),
        payload == null ? null : jsonEncode(payload),
        now,
        now,
        encodeOrigin(RelayOrigin.current),
      ],
    );
    return id;
  }

  /// Serializa a origem de uma operação para a coluna `origin_json`.
  ///
  /// `null` quando a operação é deste terminal — o caso comum, e o que faz a
  /// entrega usar a sessão local sem nenhuma indireção.
  static String? encodeOrigin(RelayOrigin? origin) =>
      origin == null ? null : jsonEncode(origin.toJson());

  /// Grava o token renovado de um terminal de origem.
  ///
  /// A fila é durável: o access token que veio com a operação vence enquanto
  /// ela espera a nuvem. Quando o principal renova (com o refresh do próprio
  /// secundário), o novo token fica gravado para as próximas tentativas — sem
  /// isto, cada tentativa renovaria de novo.
  Future<void> updateOrigin(int id, RelayOrigin origin) async {
    await database.execute(
      'UPDATE sync_queue SET origin_json = ?, updated_at = ? WHERE id = ?',
      [
        encodeOrigin(origin),
        DateTime.now().toUtc().toIso8601String(),
        id,
      ],
    );
  }

  /// Próxima operação entregável, já reservada para este processo.
  ///
  /// Devolve `null` quando não há nada elegível agora — fila vazia, tudo em
  /// backoff, ou o que resta depende de uma criação que ainda não subiu.
  Future<SyncQueueEntry?> claimNext({required String scope}) async {
    final mappings = await resolvedIds(scope: scope);
    return database.write((tx) async {
      final now = DateTime.now().toUtc();
      final rows = await tx.getAll(
        '''
        SELECT * FROM sync_queue
        WHERE scope = ? AND status IN ('PENDING', 'PROCESSING')
        ORDER BY id
        LIMIT $_scanWindow
        ''',
        [scope],
      );

      Map<String, Object?>? chosen;
      for (final row in rows) {
        final nextRetryAt = DateTime.tryParse(
          '${row['next_retry_at'] ?? ''}',
        )?.toUtc();
        if (nextRetryAt != null && nextRetryAt.isAfter(now)) continue;
        final leaseUntil = DateTime.tryParse(
          '${row['lease_until'] ?? ''}',
        )?.toUtc();
        if (leaseUntil != null && leaseUntil.isAfter(now)) continue;
        if (_hasUnresolvedDependency(row, mappings)) continue;
        chosen = row;
        break;
      }
      if (chosen == null) return null;

      await tx.execute(
        '''
        UPDATE sync_queue
        SET status = 'PROCESSING', lease_owner = ?, lease_until = ?, updated_at = ?
        WHERE id = ?
        ''',
        [
          _leaseOwner,
          now.add(leaseDuration).toIso8601String(),
          now.toIso8601String(),
          chosen['id'],
        ],
      );
      final claimed = await tx.getOptional(
        'SELECT * FROM sync_queue WHERE id = ?',
        [chosen['id']],
      );
      return claimed == null ? null : SyncQueueEntry.fromRow(claimed);
    });
  }

  /// Substitui referências a IDs locais pelo ID real já confirmado.
  Future<SyncQueueEntry> resolveReferences(
    SyncQueueEntry entry, {
    required String scope,
  }) async {
    final mappings = await resolvedIds(scope: scope);
    if (mappings.isEmpty) return entry;
    var encoded = jsonEncode({
      'path': entry.path,
      'query': entry.query,
      'payload': entry.payload,
    });
    mappings.forEach((local, remote) {
      encoded = encoded.replaceAll(local, remote);
    });
    final decoded = jsonDecode(encoded) as Map<String, dynamic>;
    return SyncQueueEntry(
      id: entry.id,
      operationId: entry.operationId,
      entityType: entry.entityType,
      entityId: mappings[entry.entityId] ?? entry.entityId,
      operation: entry.operation,
      method: entry.method,
      path: '${decoded['path']}',
      query: decoded['query'] is Map
          ? Map<String, dynamic>.from(decoded['query'] as Map)
          : null,
      payload: decoded['payload'] is Map
          ? Map<String, dynamic>.from(decoded['payload'] as Map)
          : null,
      status: entry.status,
      attempts: entry.attempts,
      createdAt: entry.createdAt,
      nextRetryAt: entry.nextRetryAt,
      lastError: entry.lastError,
      origin: entry.origin,
    );
  }

  /// Mescla campos no corpo de uma operação AINDA na fila.
  ///
  /// Existe para o caso em que uma decisão só é conhecida DEPOIS de a
  /// operação ser enfileirada — o exemplo real é a comanda de cozinha que saiu
  /// na impressora local enquanto a rede estava fora: sem marcar isso no corpo
  /// que ainda vai subir, o backend criaria um `PrintJob` novo e o cupom sairia
  /// uma segunda vez. Sem efeito se a operação já foi entregue.
  Future<bool> patchPayload(
    String operationId,
    Map<String, dynamic> patch,
  ) async {
    return database.write((tx) async {
      final row = await tx.getOptional(
        'SELECT payload FROM sync_queue WHERE operation_id = ?',
        [operationId],
      );
      if (row == null) return false;
      final raw = row['payload'];
      final decoded = raw is String && raw.isNotEmpty ? jsonDecode(raw) : null;
      final payload = decoded is Map
          ? Map<String, dynamic>.from(decoded)
          : <String, dynamic>{};
      payload.addAll(patch);
      await tx.execute(
        'UPDATE sync_queue SET payload = ?, updated_at = ? WHERE operation_id = ?',
        [
          jsonEncode(payload),
          DateTime.now().toUtc().toIso8601String(),
          operationId,
        ],
      );
      return true;
    });
  }

  /// A operação ainda está na fila esperando entrega?
  ///
  /// Uma operação recusada (`FAILED`) conta como pendente: ela também não
  /// chegou ao servidor, e quem depende disso — a impressão da comanda de
  /// cozinha — precisa assumir a responsabilidade em vez de esperar um
  /// `PrintJob` que nunca virá.
  Future<bool> isPending({
    required String scope,
    required String operationId,
  }) async {
    final row = await database.querySingle(
      'SELECT 1 FROM sync_queue WHERE scope = ? AND operation_id = ?',
      [scope, operationId],
    );
    return row != null;
  }

  /// A operação subiu. A entrada sai da fila.
  Future<void> markSynced(int id) async {
    await database.execute('DELETE FROM sync_queue WHERE id = ?', [id]);
  }

  /// Falha temporária (§23): timeout, 502, 503, sem rede. Volta para a fila
  /// com o próximo degrau da escada de backoff.
  Future<DateTime> markRetry(
    int id, {
    required int attempts,
    required String error,
    Duration? serverDelay,
  }) async {
    final delay = serverDelay ?? backoffFor(attempts);
    final nextRetryAt = DateTime.now().toUtc().add(delay);
    await database.execute(
      '''
      UPDATE sync_queue
      SET status = 'PENDING', attempts = ?, next_retry_at = ?, last_error = ?,
          lease_owner = NULL, lease_until = NULL, updated_at = ?
      WHERE id = ?
      ''',
      [
        attempts,
        nextRetryAt.toIso8601String(),
        error,
        DateTime.now().toUtc().toIso8601String(),
        id,
      ],
    );
    return nextRetryAt;
  }

  /// Falha que exige análise (§23): 400, validação, conflito, erro fiscal.
  /// Reenviar repetiria a recusa para sempre, então a operação sai da rotação
  /// e fica visível na tela de revisão.
  Future<void> markFailed(int id, {required String error}) async {
    await database.execute(
      '''
      UPDATE sync_queue
      SET status = 'FAILED', next_retry_at = NULL, last_error = ?,
          lease_owner = NULL, lease_until = NULL, updated_at = ?
      WHERE id = ?
      ''',
      [error, DateTime.now().toUtc().toIso8601String(), id],
    );
  }

  /// Devolve uma operação recusada para a fila, depois que o operador
  /// corrigiu a causa. A chave de idempotência é a mesma: se o servidor já
  /// tinha aceitado antes de recusar, o reenvio não duplica.
  Future<void> retryFailed(int id) async {
    await database.execute(
      '''
      UPDATE sync_queue
      SET status = 'PENDING', attempts = 0, next_retry_at = NULL,
          last_error = NULL, lease_owner = NULL, lease_until = NULL,
          updated_at = ?
      WHERE id = ? AND status = 'FAILED'
      ''',
      [DateTime.now().toUtc().toIso8601String(), id],
    );
  }

  /// Antecipa todos os backoffs — usado pelo botão "sincronizar agora" e
  /// quando a conectividade volta.
  Future<void> retryAllNow({required String scope}) async {
    await database.execute(
      '''
      UPDATE sync_queue
      SET next_retry_at = NULL, lease_owner = NULL, lease_until = NULL,
          status = 'PENDING'
      WHERE scope = ? AND status IN ('PENDING', 'PROCESSING')
      ''',
      [scope],
    );
  }

  /// Descarta definitivamente uma operação recusada e o que dependia dela.
  ///
  /// Só aceita como raiz uma entrada `FAILED`: uma pendente pode estar sendo
  /// enviada neste instante, e apagá-la perderia a venda em silêncio.
  Future<bool> discardFailed(int id) async {
    return database.write((tx) async {
      final row = await tx.getOptional(
        'SELECT scope, status, entity_id, created_at FROM sync_queue WHERE id = ?',
        [id],
      );
      if (row == null || '${row['status']}' != 'FAILED') return false;
      final entityId = '${row['entity_id']}';
      await tx.execute("DELETE FROM sync_queue WHERE id = ? AND status = 'FAILED'", [id]);
      if (LocalId.isTemporary(entityId)) {
        // Sem isto, as operações seguintes ficariam para sempre tentando
        // alterar um pedido que nunca existirá no servidor.
        await tx.execute(
          '''
          DELETE FROM sync_queue
          WHERE scope = ? AND id > ? AND (
            entity_id = ? OR instr(path, ?) > 0 OR
            instr(COALESCE(payload, ''), ?) > 0
          )
          ''',
          [
            '${row['scope']}',
            id,
            entityId,
            entityId,
            entityId,
          ],
        );
      }
      return true;
    });
  }

  Future<SyncQueueSummary> summary({required String scope}) async {
    final rows = await database.query(
      '''
      SELECT status, COUNT(*) AS total FROM sync_queue
      WHERE scope = ?
      GROUP BY status
      ''',
      [scope],
    );
    var pending = 0;
    var processing = 0;
    var failed = 0;
    for (final row in rows) {
      final total = (row['total'] as num?)?.toInt() ?? 0;
      switch (SyncQueueStatus.parse(row['status'])) {
        case SyncQueueStatus.processing:
          processing += total;
        case SyncQueueStatus.failed:
          failed += total;
        case SyncQueueStatus.pending:
        case SyncQueueStatus.synced:
          pending += total;
      }
    }
    return SyncQueueSummary(
      pending: pending,
      processing: processing,
      failed: failed,
    );
  }

  Future<List<SyncQueueEntry>> entries({
    required String scope,
    bool onlyFailed = false,
    int limit = 200,
  }) async {
    final rows = await database.query(
      '''
      SELECT * FROM sync_queue
      WHERE scope = ? ${onlyFailed ? "AND status = 'FAILED'" : ''}
      ORDER BY id
      LIMIT ?
      ''',
      [scope, limit],
    );
    return rows.map(SyncQueueEntry.fromRow).toList();
  }

  /// Registra que um ID local virou definitivo e reescreve o que ainda está
  /// na fila apontando para ele.
  Future<void> registerResolvedId({
    required String scope,
    required String localId,
    required String remoteId,
  }) async {
    if (localId.isEmpty || remoteId.isEmpty || localId == remoteId) return;
    await database.write((tx) async {
      await tx.execute(
        '''
        INSERT INTO id_map(scope, local_id, remote_id, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(scope, local_id) DO UPDATE SET remote_id = excluded.remote_id
        ''',
        [scope, localId, remoteId, DateTime.now().toUtc().toIso8601String()],
      );
      await tx.execute(
        '''
        UPDATE sync_queue SET
          path = replace(path, ?, ?),
          query_json = replace(COALESCE(query_json, ''), ?, ?),
          payload = replace(COALESCE(payload, ''), ?, ?),
          entity_id = CASE WHEN entity_id = ? THEN ? ELSE entity_id END
        WHERE scope = ?
        ''',
        [
          localId,
          remoteId,
          localId,
          remoteId,
          localId,
          remoteId,
          localId,
          remoteId,
          scope,
        ],
      );
    });
  }

  Future<Map<String, String>> resolvedIds({required String scope}) async {
    final rows = await database.query(
      'SELECT local_id, remote_id FROM id_map WHERE scope = ?',
      [scope],
    );
    return {
      for (final row in rows) '${row['local_id']}': '${row['remote_id']}',
    };
  }

  /// Degrau de backoff da tentativa informada (1-based).
  static Duration backoffFor(int attempts) {
    final index = min(max(attempts - 1, 0), retryLadder.length - 1);
    return retryLadder[index];
  }

  /// A operação ainda cita um ID temporário que não virou real?
  ///
  /// É o que distingue "depende de uma criação que não subiu" de "é
  /// independente e pode passar na frente". Sem isso, pular a fila enviaria a
  /// inclusão de um item antes de o pedido que o contém existir no servidor.
  static bool _hasUnresolvedDependency(
    Map<String, Object?> row,
    Map<String, String> mappings,
  ) {
    var remaining = [
      '${row['path'] ?? ''}',
      '${row['query_json'] ?? ''}',
      '${row['payload'] ?? ''}',
    ].join(' ');
    if (!remaining.contains(LocalId.temporaryPrefix)) return false;
    // Os campos `client_*_id` carregam identificadores que ESTA operação está
    // criando (o item, o pagamento, a movimentação) — eles vão no corpo
    // justamente para o servidor deduplicar. Confundi-los com dependências
    // deixava a inclusão de item presa na fila para sempre, porque ela
    // esperava por um identificador que só ela mesma poderia resolver.
    remaining = remaining.replaceAll(_clientIdField, '');
    // O identificador temporário que uma CRIAÇÃO está gerando não é uma
    // dependência — é o que ela vai resolver. Sem esta exceção, a própria
    // criação do pedido nunca seria elegível e a fila travaria de saída.
    //
    // A exceção vale só para `CREATE`: uma alteração sobre a mesma entidade
    // temporária (lançar item, fechar, pagar) depende de a criação ter subido
    // antes, e liberá-la aqui mandaria ao servidor uma referência a um pedido
    // que ele não conhece.
    if (SyncOperation.parse(row['operation']) == SyncOperation.create) {
      final own = '${row['entity_id'] ?? ''}';
      if (own.isNotEmpty) remaining = remaining.replaceAll(own, '');
    }
    for (final local in mappings.keys) {
      remaining = remaining.replaceAll(local, '');
    }
    return remaining.contains(LocalId.temporaryPrefix);
  }
}
