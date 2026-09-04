import 'dart:convert';
import 'dart:math';

import 'local_id.dart';
import 'pdv_database.dart';

/// Situação do documento fiscal, independente da situação da venda (§16).
///
/// Os quatro estados originais (`pending/processing/authorized/failed`) não
/// davam conta do que o terminal precisa decidir quando está sozinho. "Falhou"
/// cobria desde uma queda de rede — que se resolve tentando de novo — até uma
/// rejeição tributária, que só piora com retentativa. E "autorizado" era
/// gravado para qualquer HTTP bem-sucedido, inclusive para uma resposta que
/// dizia, com todas as letras, que a nota não tinha sido emitida.
enum FiscalStatus {
  /// Enfileirado; nunca chegou ao servidor.
  pending,

  /// Enviado e aceito; a SEFAZ ainda não respondeu. Reconsultar, não reenviar.
  processing,

  /// Autorizado pela SEFAZ. Só aqui existe documento fiscal para o cliente.
  authorized,

  /// Recusa definitiva (rejeição tributária, documento inválido).
  /// Reenviar repete a recusa: precisa de correção humana.
  rejected,

  /// Certificado, CSC, token ou cadastro fiscal inválido. Nenhuma nota sai
  /// enquanto não for corrigido — e não é problema deste pedido.
  configurationError,

  /// A emissão pode ter acontecido do outro lado e a resposta se perdeu.
  /// Consultar antes de qualquer reenvio; reenviar às cegas duplica a nota.
  reconciliationRequired,

  cancelled,

  /// Falha local sem classificação (bug, resposta ilegível). Não retenta
  /// sozinha para não insistir num erro que não se entende.
  failed;

  String get code => switch (this) {
    FiscalStatus.configurationError => 'CONFIGURATION_ERROR',
    FiscalStatus.reconciliationRequired => 'RECONCILIATION_REQUIRED',
    _ => name.toUpperCase(),
  };

  /// Vale a pena tocar neste documento de novo?
  ///
  /// `reconciliationRequired` entra porque a ação seguinte é uma CONSULTA — a
  /// emissão do StarChef é idempotente por pedido, então repetir o POST devolve
  /// a nota que já existe em vez de criar uma segunda.
  bool get isRetryable => switch (this) {
    FiscalStatus.pending ||
    FiscalStatus.processing ||
    FiscalStatus.reconciliationRequired => true,
    _ => false,
  };

  /// Acabou: nem retentativa nem espera resolvem mais nada.
  bool get isSettled => !isRetryable;

  /// Existe documento fiscal entregável ao consumidor?
  bool get hasFiscalDocument => this == FiscalStatus.authorized;

  static FiscalStatus parse(Object? raw) => switch ('$raw'.toUpperCase()) {
    'PROCESSING' => FiscalStatus.processing,
    'AUTHORIZED' => FiscalStatus.authorized,
    'REJECTED' => FiscalStatus.rejected,
    'CONFIGURATION_ERROR' => FiscalStatus.configurationError,
    'RECONCILIATION_REQUIRED' => FiscalStatus.reconciliationRequired,
    'CANCELLED' => FiscalStatus.cancelled,
    'FAILED' => FiscalStatus.failed,
    _ => FiscalStatus.pending,
  };

  /// Lê a situação fiscal REAL de uma resposta de `/invoices/emit/`.
  ///
  /// O backend manda `fiscal_state` justamente porque `Invoice.status` sozinho
  /// não distingue "ainda não saiu daqui" de "pode ter sido emitida". Quando o
  /// campo não vem (servidor antigo), cai no que dá para inferir — e o padrão
  /// é `pending`, nunca `authorized`: presumir autorização é o erro caro.
  static FiscalStatus fromResponse(Map<String, dynamic> response) {
    final state = '${response['fiscal_state'] ?? ''}'.toLowerCase();
    if (state.isNotEmpty) {
      return switch (state) {
        'authorized' => FiscalStatus.authorized,
        'cancelled' => FiscalStatus.cancelled,
        'rejected' => FiscalStatus.rejected,
        'configuration_error' => FiscalStatus.configurationError,
        'reconciliation_required' => FiscalStatus.reconciliationRequired,
        // Contingência legada continua sendo uma nota que ainda não voltou.
        'processing' || 'contingency_pending' => FiscalStatus.processing,
        'awaiting_transmission' || 'draft' => FiscalStatus.pending,
        _ => FiscalStatus.pending,
      };
    }
    if (response['emitted'] == false) return FiscalStatus.configurationError;
    return switch ('${response['status'] ?? ''}'.toLowerCase()) {
      'issued' => FiscalStatus.authorized,
      'cancelled' => FiscalStatus.cancelled,
      'error' => FiscalStatus.rejected,
      'pending' => FiscalStatus.processing,
      _ => FiscalStatus.pending,
    };
  }
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
    this.snapshot,
    this.response,
    this.invoiceId,
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

  /// O corpo enviado a `/invoices/emit/`.
  final Map<String, dynamic> payload;

  /// Retrato fiscal do pedido no instante do pagamento: emitente, itens com a
  /// tributação já resolvida, pagamentos e consumidor. É imutável de propósito
  /// — se o cadastro do produto mudar amanhã, a nota desta venda continua
  /// sendo a desta venda.
  final Map<String, dynamic>? snapshot;

  /// Última resposta recebida, guardada separada do pedido. Antes a resposta
  /// sobrescrevia `payload` e o que tinha sido enviado se perdia.
  final Map<String, dynamic>? response;

  final String? invoiceId;
  final FiscalStatus status;
  final int attempts;
  final DateTime createdAt;
  final DateTime? nextRetryAt;
  final String? lastError;
  final String? protocol;

  static Map<String, dynamic>? _decodeMap(Object? raw) {
    if (raw == null) return null;
    final decoded = jsonDecode('$raw');
    return decoded is Map ? Map<String, dynamic>.from(decoded) : null;
  }

  static FiscalDocument fromRow(Map<String, Object?> row) {
    return FiscalDocument(
      id: (row['id'] as num?)?.toInt() ?? 0,
      documentId: '${row['document_id']}',
      orderId: '${row['order_id']}',
      payload: _decodeMap(row['payload']) ?? <String, dynamic>{},
      snapshot: _decodeMap(row['snapshot']),
      response: _decodeMap(row['response']),
      invoiceId: row['invoice_id'] as String?,
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

  static const _retryableCodes = "('PENDING', 'PROCESSING', 'RECONCILIATION_REQUIRED')";

  final PdvDatabase database;

  /// Registra a intenção de emitir. Devolve o identificador do documento.
  Future<FiscalDocument> enqueue({
    required String scope,
    required String orderId,
    required Map<String, dynamic> payload,
    Map<String, dynamic>? snapshot,
  }) async {
    final documentId = '${payload['client_document_id'] ?? LocalId.uuid()}';
    final now = DateTime.now().toUtc().toIso8601String();
    await database.execute(
      '''
      INSERT INTO fiscal_queue(
        document_id, scope, order_id, payload, snapshot, status, attempts,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, 'PENDING', 0, ?, ?)
      ON CONFLICT(document_id) DO NOTHING
      ''',
      [
        documentId,
        scope,
        orderId,
        jsonEncode({...payload, 'client_document_id': documentId}),
        snapshot == null ? null : jsonEncode(snapshot),
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
  /// Reserva a nota de UM pedido, mesmo que outras estejam na frente.
  ///
  /// Usado quando o operador esta esperando o cupom fiscal daquela venda:
  /// a ordem da fila importa para o laco de fundo, nao para o gesto que
  /// tem alguem parado no balcao.
  Future<FiscalDocument?> claimForOrder({
    required String scope,
    required String orderId,
  }) => _claim(scope: scope, orderId: orderId);

  Future<FiscalDocument?> claimNext({required String scope}) =>
      _claim(scope: scope);

  Future<FiscalDocument?> _claim({
    required String scope,
    String? orderId,
  }) async {
    return database.write((tx) async {
      final now = DateTime.now().toUtc();
      // Com alvo, o backoff nao vale: quem pediu esta esperando o papel.
      final row = await tx.getOptional(
        orderId == null
            ? '''
        SELECT * FROM fiscal_queue
        WHERE scope = ? AND status IN $_retryableCodes
          AND (next_retry_at IS NULL OR next_retry_at <= ?)
        ORDER BY id
        LIMIT 1
        '''
            : '''
        SELECT * FROM fiscal_queue
        WHERE scope = ? AND status IN $_retryableCodes AND order_id = ?
        ORDER BY id DESC
        LIMIT 1
        ''',
        [scope, orderId ?? now.toIso8601String()],
      );
      if (row == null) return null;
      await tx.execute(
        "UPDATE fiscal_queue SET status = 'PROCESSING', updated_at = ? WHERE id = ?",
        [now.toIso8601String(), row['id']],
      );
      return FiscalDocument.fromRow(row);
    });
  }

  /// Grava a situação fiscal que o servidor informou.
  ///
  /// Um estado ainda em andamento (`pending`, `processing`,
  /// `reconciliationRequired`) volta para a escada de retentativa; um estado
  /// final para de ser tentado. O `payload` original nunca é sobrescrito: a
  /// resposta vai para a própria coluna.
  Future<DateTime?> applyOutcome(
    int id, {
    required FiscalStatus status,
    required int attempts,
    Map<String, dynamic>? response,
    String? error,
  }) async {
    final now = DateTime.now().toUtc();
    final protocol = response == null
        ? null
        : '${response['authorization_protocol'] ?? response['protocol'] ?? ''}';
    final invoiceId = response == null ? null : '${response['id'] ?? ''}';
    DateTime? nextRetryAt;
    if (status.isRetryable) {
      nextRetryAt = now.add(
        retryLadder[min(max(attempts - 1, 0), retryLadder.length - 1)],
      );
    }
    await database.execute(
      '''
      UPDATE fiscal_queue
      SET status = ?, attempts = ?, next_retry_at = ?, last_error = ?,
          protocol = COALESCE(NULLIF(?, ''), protocol),
          invoice_id = COALESCE(NULLIF(?, ''), invoice_id),
          response = COALESCE(?, response),
          updated_at = ?
      WHERE id = ?
      ''',
      [
        status.code,
        attempts,
        nextRetryAt?.toIso8601String(),
        error,
        protocol,
        invoiceId,
        response == null ? null : jsonEncode(response),
        now.toIso8601String(),
        id,
      ],
    );
    return nextRetryAt;
  }

  /// Falha de transporte: nada se sabe sobre o documento, só que a chamada não
  /// completou. Volta para `PENDING` e tenta de novo mais tarde.
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

  /// Recusa definitiva ou erro sem classificação: insistir repetiria o mesmo.
  Future<void> markFailed(
    int id, {
    required String error,
    FiscalStatus status = FiscalStatus.failed,
  }) async {
    await database.execute(
      '''
      UPDATE fiscal_queue
      SET status = ?, next_retry_at = NULL, last_error = ?, updated_at = ?
      WHERE id = ?
      ''',
      [
        status.code,
        error,
        DateTime.now().toUtc().toIso8601String(),
        id,
      ],
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

  /// O ultimo documento fiscal deste pedido, com a resposta que o
  /// servidor devolveu. E o que permite imprimir o DANFE logo depois de
  /// drenar a fila, sem uma segunda ida a rede so para saber se a nota
  /// foi autorizada.
  Future<FiscalDocument?> latestForOrder({
    required String scope,
    required String orderId,
  }) async {
    final row = await database.querySingle(
      '''
      SELECT * FROM fiscal_queue
      WHERE scope = ? AND order_id = ?
      ORDER BY id DESC LIMIT 1
      ''',
      [scope, orderId],
    );
    return row == null ? null : FiscalDocument.fromRow(row);
  }

  Future<int> pendingCount({required String scope}) async {
    final row = await database.querySingle(
      '''
      SELECT COUNT(*) AS total FROM fiscal_queue
      WHERE scope = ? AND status IN $_retryableCodes
      ''',
      [scope],
    );
    return (row?['total'] as num?)?.toInt() ?? 0;
  }

  /// Documentos que pararam e precisam de alguém: rejeição, configuração ou
  /// falha. Não entram em `pendingCount` porque esperar não os resolve.
  Future<int> blockedCount({required String scope}) async {
    final row = await database.querySingle(
      '''
      SELECT COUNT(*) AS total FROM fiscal_queue
      WHERE scope = ? AND status IN ('REJECTED', 'CONFIGURATION_ERROR', 'FAILED')
      ''',
      [scope],
    );
    return (row?['total'] as num?)?.toInt() ?? 0;
  }
}
