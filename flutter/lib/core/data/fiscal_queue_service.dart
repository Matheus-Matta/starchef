import 'dart:convert';
import 'dart:math';

import 'local_id.dart';
import 'pdv_database.dart';

/// Situação do documento fiscal, independente da situação da venda (§16).
enum FiscalStatus {
  pending,
  processing,
  authorized,
  failed;

  String get code => name.toUpperCase();

  static FiscalStatus parse(Object? raw) => switch ('$raw'.toUpperCase()) {
    'PROCESSING' => FiscalStatus.processing,
    'AUTHORIZED' => FiscalStatus.authorized,
    'FAILED' => FiscalStatus.failed,
    _ => FiscalStatus.pending,
  };
}

class FiscalDocument {
  const FiscalDocument({
    required this.id,
    required this.documentId,
    required this.orderId,
    required this.payload,
    required this.status,
    required this.attempts,
    required this.createdAt,
    this.nextRetryAt,
    this.lastError,
    this.protocol,
  });

  final int id;

  /// UUID gerado no terminal antes de qualquer tentativa de emissão (§7).
  /// É a chave de idempotência: uma emissão reenviada depois de um timeout
  /// não pode virar duas notas.
  final String documentId;

  final String orderId;
  final Map<String, dynamic> payload;
  final FiscalStatus status;
  final int attempts;
  final DateTime createdAt;
  final DateTime? nextRetryAt;
  final String? lastError;
  final String? protocol;

  static FiscalDocument fromRow(Map<String, Object?> row) {
    final decoded = jsonDecode('${row['payload']}');
    return FiscalDocument(
      id: (row['id'] as num?)?.toInt() ?? 0,
      documentId: '${row['document_id']}',
      orderId: '${row['order_id']}',
      payload: decoded is Map
          ? Map<String, dynamic>.from(decoded)
          : <String, dynamic>{},
      status: FiscalStatus.parse(row['status']),
      attempts: (row['attempts'] as num?)?.toInt() ?? 0,
      createdAt:
          DateTime.tryParse('${row['created_at']}')?.toUtc() ??
          DateTime.now().toUtc(),
      nextRetryAt: DateTime.tryParse('${row['next_retry_at'] ?? ''}')?.toUtc(),
      lastError: row['last_error'] as String?,
      protocol: row['protocol'] as String?,
    );
  }
}

/// Fila própria dos documentos fiscais (§16).
///
/// O ponto da separação: **a venda não depende da nota**. Antes, `/invoices/`
/// estava na lista de rotas que exigem servidor, então uma SEFAZ fora do ar ou
/// simplesmente a internet caída devolviam erro na tela no meio do
/// recebimento. A venda termina localmente (`COMPLETED`) e o documento fica
/// `PENDING` até que a emissão seja possível.
///
/// A fila é separada da [SyncQueueService] de propósito: a emissão tem
/// cadência, prioridade e diagnóstico próprios, e um documento recusado pela
/// SEFAZ não pode segurar a sincronização das vendas.
class FiscalQueueService {
  FiscalQueueService({required this.database});

  /// Emissão fiscal tolera esperas maiores que a sincronização comum: a SEFAZ
  /// costuma voltar em minutos, e insistir de segundo em segundo só gera
  /// rejeição por excesso de consultas.
  static const retryLadder = [
    Duration(seconds: 15),
    Duration(seconds: 30),
    Duration(minutes: 1),
    Duration(minutes: 5),
    Duration(minutes: 15),
  ];

  final PdvDatabase database;

  /// Registra a intenção de emitir. Devolve o identificador do documento.
  Future<FiscalDocument> enqueue({
    required String scope,
    required String orderId,
    required Map<String, dynamic> payload,
  }) async {
    final documentId = '${payload['client_document_id'] ?? LocalId.uuid()}';
    final now = DateTime.now().toUtc().toIso8601String();
    await database.execute(
      '''
      INSERT INTO fiscal_queue(
        document_id, scope, order_id, payload, status, attempts,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, 'PENDING', 0, ?, ?)
      ON CONFLICT(document_id) DO NOTHING
      ''',
      [
        documentId,
        scope,
        orderId,
        jsonEncode({...payload, 'client_document_id': documentId}),
        now,
        now,
      ],
    );
    final row = await database.querySingle(
      'SELECT * FROM fiscal_queue WHERE document_id = ?',
      [documentId],
    );
    return FiscalDocument.fromRow(row!);
  }

  /// Próximo documento emitível. `null` quando não há nada elegível agora.
  Future<FiscalDocument?> claimNext({required String scope}) async {
    return database.write((tx) async {
      final now = DateTime.now().toUtc();
      final row = await tx.getOptional(
        '''
        SELECT * FROM fiscal_queue
        WHERE scope = ? AND status IN ('PENDING', 'PROCESSING')
          AND (next_retry_at IS NULL OR next_retry_at <= ?)
        ORDER BY id
        LIMIT 1
        ''',
        [scope, now.toIso8601String()],
      );
      if (row == null) return null;
      await tx.execute(
        "UPDATE fiscal_queue SET status = 'PROCESSING', updated_at = ? WHERE id = ?",
        [now.toIso8601String(), row['id']],
      );
      return FiscalDocument.fromRow(row);
    });
  }

  Future<void> markAuthorized(
    int id, {
    String? protocol,
    Map<String, dynamic>? response,
  }) async {
    await database.execute(
      '''
      UPDATE fiscal_queue
      SET status = 'AUTHORIZED', protocol = ?, last_error = NULL,
          next_retry_at = NULL, updated_at = ?,
          payload = COALESCE(?, payload)
      WHERE id = ?
      ''',
      [
        protocol,
        DateTime.now().toUtc().toIso8601String(),
        response == null ? null : jsonEncode(response),
        id,
      ],
    );
  }

  Future<DateTime> markRetry(
    int id, {
    required int attempts,
    required String error,
  }) async {
    final delay =
        retryLadder[min(max(attempts - 1, 0), retryLadder.length - 1)];
    final nextRetryAt = DateTime.now().toUtc().add(delay);
    await database.execute(
      '''
      UPDATE fiscal_queue
      SET status = 'PENDING', attempts = ?, next_retry_at = ?, last_error = ?,
          updated_at = ?
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

  /// Rejeição da SEFAZ ou erro de validação: insistir repetiria a recusa.
  Future<void> markFailed(int id, {required String error}) async {
    await database.execute(
      '''
      UPDATE fiscal_queue
      SET status = 'FAILED', next_retry_at = NULL, last_error = ?, updated_at = ?
      WHERE id = ?
      ''',
      [error, DateTime.now().toUtc().toIso8601String(), id],
    );
  }

  Future<List<FiscalDocument>> documents({
    required String scope,
    FiscalStatus? status,
    int limit = 100,
  }) async {
    final rows = await database.query(
      '''
      SELECT * FROM fiscal_queue
      WHERE scope = ? ${status == null ? '' : 'AND status = ?'}
      ORDER BY id DESC
      LIMIT ?
      ''',
      [scope, if (status != null) status.code, limit],
    );
    return rows.map(FiscalDocument.fromRow).toList();
  }

  /// Situação fiscal de uma venda, para a tela mostrar
  /// "Venda concluída · Nota pendente".
  Future<FiscalStatus?> statusForOrder({
    required String scope,
    required String orderId,
  }) async {
    final row = await database.querySingle(
      '''
      SELECT status FROM fiscal_queue
      WHERE scope = ? AND order_id = ?
      ORDER BY id DESC LIMIT 1
      ''',
      [scope, orderId],
    );
    return row == null ? null : FiscalStatus.parse(row['status']);
  }

  Future<int> pendingCount({required String scope}) async {
    final row = await database.querySingle(
      '''
      SELECT COUNT(*) AS total FROM fiscal_queue
      WHERE scope = ? AND status IN ('PENDING', 'PROCESSING')
      ''',
      [scope],
    );
    return (row?['total'] as num?)?.toInt() ?? 0;
  }
}
