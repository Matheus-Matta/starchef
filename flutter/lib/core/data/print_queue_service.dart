import 'dart:convert';
import 'dart:math';

import 'local_id.dart';
import 'pdv_database.dart';

enum PrintJobStatus {
  pending,
  printing,
  printed,
  failed;

  String get code => name.toUpperCase();

  static PrintJobStatus parse(Object? raw) => switch ('$raw'.toUpperCase()) {
    'PRINTING' => PrintJobStatus.printing,
    'PRINTED' => PrintJobStatus.printed,
    'FAILED' => PrintJobStatus.failed,
    _ => PrintJobStatus.pending,
  };
}

/// Um cupom esperando a impressora.
class PrintQueueEntry {
  const PrintQueueEntry({
    required this.id,
    required this.jobId,
    required this.printerId,
    required this.printer,
    required this.jobType,
    required this.content,
    required this.status,
    required this.attempts,
    required this.createdAt,
    this.remoteJobId,
    this.barcode,
    this.qr,
    this.nextRetryAt,
    this.lastError,
  });

  final int id;

  /// Identificador do trabalho neste terminal.
  final String jobId;

  /// Identificador do `PrintJob` no servidor, quando ele veio de lá. É o que
  /// permite confirmar a impressão depois e o que impede o mesmo cupom de
  /// entrar duas vezes na fila.
  final String? remoteJobId;

  final String printerId;

  /// Cópia do cadastro da impressora no momento em que o cupom entrou. Se o
  /// cadastro mudar entre a fila e o papel, o trabalho ainda sai no
  /// equipamento para o qual foi montado.
  final Map<String, dynamic> printer;

  final String jobType;
  final String content;
  final String? barcode;
  final String? qr;
  final PrintJobStatus status;
  final int attempts;
  final DateTime createdAt;
  final DateTime? nextRetryAt;
  final String? lastError;

  static PrintQueueEntry fromRow(Map<String, Object?> row) {
    final decoded = jsonDecode('${row['printer_json']}');
    return PrintQueueEntry(
      id: (row['id'] as num?)?.toInt() ?? 0,
      jobId: '${row['job_id']}',
      remoteJobId: row['remote_job_id'] as String?,
      printerId: '${row['printer_id']}',
      printer: decoded is Map
          ? Map<String, dynamic>.from(decoded)
          : <String, dynamic>{},
      jobType: '${row['job_type']}',
      content: '${row['content']}',
      barcode: row['barcode'] as String?,
      qr: row['qr'] as String?,
      status: PrintJobStatus.parse(row['status']),
      attempts: (row['attempts'] as num?)?.toInt() ?? 0,
      createdAt:
          DateTime.tryParse('${row['created_at']}')?.toUtc() ??
          DateTime.now().toUtc(),
      nextRetryAt: DateTime.tryParse('${row['next_retry_at'] ?? ''}')?.toUtc(),
      lastError: row['last_error'] as String?,
    );
  }
}

/// O que aconteceu com um cupom depois de uma falha de impressão.
///
/// Devolver só a data da próxima tentativa escondia o caso que interessa: o
/// trabalho que gastou todas as tentativas e parou de girar sozinho.
class PrintRetryOutcome {
  const PrintRetryOutcome({
    required this.attempts,
    required this.exhausted,
    this.nextRetryAt,
  });

  final int attempts;

  /// Quando ele volta a ser tentado. `null` quando as tentativas acabaram.
  final DateTime? nextRetryAt;

  /// Chegou ao teto: agora depende de uma decisão do operador.
  final bool exhausted;
}

class PrintQueueSummary {
  const PrintQueueSummary({this.pending = 0, this.failed = 0});

  final int pending;
  final int failed;

  int get total => pending + failed;
  bool get hasWork => pending > 0;
}

/// **A fila de impressão é do terminal, não do servidor** (§17).
///
/// Antes ela vivia no backend: o agente perguntava `/print-jobs/` e imprimia o
/// que viesse. Com a internet fora não havia o que perguntar, e nada saía no
/// papel — nem um cupom montado aqui mesmo. Pior: uma impressora sem papel
/// simplesmente perdia o trabalho, porque não existia nada guardando o que
/// faltava imprimir.
///
/// Agora existe um lugar só onde os cupons esperam, alimentado por duas
/// fontes: o que este terminal montou (recibo, comanda, cancelamento, nota de
/// pesagem, teste) e o que o servidor gerou. Um executor, uma ordem, uma
/// retentativa.
class PrintQueueService {
  PrintQueueService({required this.database, String? leaseOwner})
    : _leaseOwner = leaseOwner ?? 'spooler-${LocalId.uuid()}';

  /// Este documento já saiu no papel neste terminal?
  ///
  /// A pergunta é sobre a NOTA, não sobre o trabalho de impressão: dois
  /// trabalhos diferentes para a mesma nota fiscal são exatamente o que fazia
  /// o cliente receber dois DANFEs idênticos.
  Future<bool> wasDocumentPrinted({
    required String scope,
    required String dedupeKey,
  }) async {
    if (dedupeKey.isEmpty) return false;
    final row = await database.querySingle(
      'SELECT 1 FROM printed_documents WHERE scope = ? AND dedupe_key = ?',
      [scope, dedupeKey],
    );
    return row != null;
  }

  /// Registra que este documento saiu no papel neste terminal.
  Future<void> markDocumentPrinted({
    required String scope,
    required String dedupeKey,
  }) async {
    if (dedupeKey.isEmpty) return;
    await database.execute(
      '''
      INSERT INTO printed_documents(scope, dedupe_key, printed_at)
      VALUES (?, ?, ?)
      ON CONFLICT(scope, dedupe_key) DO UPDATE SET printed_at = excluded.printed_at
      ''',
      [scope, dedupeKey, DateTime.now().toUtc().toIso8601String()],
    );
  }

  /// Escada de espera entre tentativas: cada falha espera mais que a anterior.
  ///
  /// Começa em segundos porque a causa mais comum (papel, cabo, impressora
  /// desligada) se resolve assim, e quem espera o cupom é uma pessoa no
  /// balcão. Vai afrouxando porque, passados alguns minutos, insistir no mesmo
  /// ritmo não resolve nada e ainda custa um tempo limite por rodada — tempo
  /// em que os cupons das outras impressoras ficam esperando a vez.
  ///
  /// Há exatamente uma espera por tentativa permitida: o tamanho desta lista
  /// **é** o teto de [maximumAttempts]. Somadas, dão cerca de 1h20 de
  /// insistência antes de o cupom pedir uma decisão humana.
  static const retryLadder = [
    Duration(seconds: 5),
    Duration(seconds: 10),
    Duration(seconds: 20),
    Duration(seconds: 30),
    Duration(seconds: 45),
    Duration(minutes: 1),
    Duration(seconds: 90),
    Duration(minutes: 2),
    Duration(minutes: 3),
    Duration(minutes: 4),
    Duration(minutes: 5),
    Duration(minutes: 7),
    Duration(minutes: 10),
    Duration(minutes: 12),
    Duration(minutes: 15),
  ];

  /// Quantas vezes o mesmo cupom é tentado antes de parar e esperar alguém.
  ///
  /// Sem teto, um trabalho que ninguém vai conseguir imprimir (impressora
  /// desinstalada, endereço trocado, setor sem equipamento) girava até expirar
  /// em 12 h — centenas de tentativas, cada uma custando um tempo limite
  /// inteiro e atrasando os cupons bons atrás dele. Quinze cobrem com folga
  /// uma troca de papel ou um religar de impressora; depois disso o cupom fica
  /// visível na tela da fila, onde o operador decide entre tentar de novo
  /// (o que zera esta contagem) e descartar.
  static int get maximumAttempts => retryLadder.length;

  /// Depois disso o cupom não interessa mais a ninguém: uma comanda de ontem
  /// saindo hoje confunde a cozinha mais do que ajuda.
  static const expiresAfter = Duration(hours: 12);

  static const leaseDuration = Duration(seconds: 60);

  final PdvDatabase database;
  final String _leaseOwner;

  /// Coloca um cupom na fila. Repetir a mesma origem não duplica o papel.
  ///
  /// [remoteJobId] identifica o `PrintJob` do servidor: enquanto o
  /// `mark-printed` não é confirmado, o mesmo trabalho volta a aparecer na
  /// consulta, e sem esta chave ele entraria de novo na fila.
  /// [heldReason] entra o cupom **parado**, esperando uma decisão de quem
  /// está no balcão em vez de ir direto para a impressora. É como um trabalho
  /// herdado é recebido: ele existe, aparece na tela da fila e sai com "tentar
  /// agora" — mas ninguém manda papel por conta própria em nome de um
  /// terminal que não era o dono dele.
  Future<String> enqueue({
    required String scope,
    required Map<String, dynamic> printer,
    required String jobType,
    required String content,
    String? jobId,
    String? remoteJobId,
    String? barcode,
    String? qr,
    String? heldReason,
  }) async {
    final id = jobId ?? remoteJobId ?? LocalId.uuid();
    final now = DateTime.now().toUtc().toIso8601String();
    await database.execute(
      '''
      INSERT INTO print_queue(
        job_id, scope, remote_job_id, printer_id, printer_json, job_type,
        content, barcode, qr, status, attempts, last_error, created_at,
        updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
      ON CONFLICT(job_id) DO NOTHING
      ''',
      [
        id,
        scope,
        remoteJobId,
        '${printer['id'] ?? ''}',
        jsonEncode(printer),
        jobType,
        content,
        barcode,
        qr,
        heldReason == null ? 'PENDING' : 'FAILED',
        heldReason,
        now,
        now,
      ],
    );
    return id;
  }

  /// Próximo cupom a sair, já reservado para este processo.
  ///
  /// A reserva importa porque o PDV e a janela da Balança Rápida compartilham
  /// o banco: sem ela, os dois pegariam o mesmo trabalho e o papel sairia
  /// duas vezes.
  Future<PrintQueueEntry?> claimNext({required String scope}) async {
    return database.write((tx) async {
      final now = DateTime.now().toUtc();
      final row = await tx.getOptional(
        '''
        SELECT * FROM print_queue
        WHERE scope = ? AND status IN ('PENDING', 'PRINTING')
          AND (next_retry_at IS NULL OR next_retry_at <= ?)
          AND (lease_until IS NULL OR lease_until <= ?)
        ORDER BY id
        LIMIT 1
        ''',
        [scope, now.toIso8601String(), now.toIso8601String()],
      );
      if (row == null) return null;

      final createdAt = DateTime.tryParse('${row['created_at']}')?.toUtc();
      if (createdAt != null && now.difference(createdAt) > expiresAfter) {
        await tx.execute(
          '''
          UPDATE print_queue
          SET status = 'FAILED', last_error = ?, updated_at = ?
          WHERE id = ?
          ''',
          [
            'Trabalho expirado sem conseguir imprimir.',
            now.toIso8601String(),
            row['id'],
          ],
        );
        return null;
      }

      await tx.execute(
        '''
        UPDATE print_queue
        SET status = 'PRINTING', lease_owner = ?, lease_until = ?, updated_at = ?
        WHERE id = ?
        ''',
        [
          _leaseOwner,
          now.add(leaseDuration).toIso8601String(),
          now.toIso8601String(),
          row['id'],
        ],
      );
      // Relê depois da reserva: devolver a linha antiga entregaria ao chamador
      // um trabalho que se diz `PENDING` quando ele já está reservado.
      final claimed = await tx.getOptional(
        'SELECT * FROM print_queue WHERE id = ?',
        [row['id']],
      );
      return claimed == null ? null : PrintQueueEntry.fromRow(claimed);
    });
  }

  /// O papel saiu.
  Future<void> markPrinted(int id) async {
    final now = DateTime.now().toUtc().toIso8601String();
    await database.execute(
      '''
      UPDATE print_queue
      SET status = 'PRINTED', printed_at = ?, updated_at = ?, last_error = NULL,
          lease_owner = NULL, lease_until = NULL
      WHERE id = ?
      ''',
      [now, now, id],
    );
  }

  /// Falha de comunicação com a impressora: papel, cabo, equipamento
  /// desligado. Volta para a fila — desistir aqui perderia a comanda.
  ///
  /// Só até [maximumAttempts]: insistir para sempre num equipamento que não
  /// vai responder não imprime nada e atrasa o que ainda tem chance.
  Future<PrintRetryOutcome> markRetry(
    int id, {
    required int attempts,
    required String error,
  }) async {
    if (attempts >= maximumAttempts) {
      await markFailed(
        id,
        error: 'Depois de $maximumAttempts tentativas: $error',
        attempts: attempts,
      );
      return PrintRetryOutcome(attempts: attempts, exhausted: true);
    }
    final delay = backoffFor(attempts);
    final nextRetryAt = DateTime.now().toUtc().add(delay);
    await database.execute(
      '''
      UPDATE print_queue
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
    return PrintRetryOutcome(
      attempts: attempts,
      nextRetryAt: nextRetryAt,
      exhausted: false,
    );
  }

  /// Erro que nenhuma repetição resolve: trabalho sem conteúdo, impressora
  /// sem endereço configurado.
  Future<void> markFailed(
    int id, {
    required String error,
    int? attempts,
  }) async {
    await database.execute(
      '''
      UPDATE print_queue
      SET status = 'FAILED', next_retry_at = NULL, last_error = ?,
          attempts = COALESCE(?, attempts),
          lease_owner = NULL, lease_until = NULL, updated_at = ?
      WHERE id = ?
      ''',
      [error, attempts, DateTime.now().toUtc().toIso8601String(), id],
    );
  }

  /// Recoloca um trabalho recusado na fila, depois que o operador resolveu a
  /// causa (trocou o papel, religou a impressora).
  Future<void> retryFailed(int id) async {
    await database.execute(
      '''
      UPDATE print_queue
      SET status = 'PENDING', attempts = 0, next_retry_at = NULL,
          last_error = NULL, updated_at = ?
      WHERE id = ? AND status = 'FAILED'
      ''',
      [DateTime.now().toUtc().toIso8601String(), id],
    );
  }

  /// Antecipa a espera de UM trabalho, ou traz de volta um recusado.
  ///
  /// É o "tentar agora" da tela da fila: o operador trocou o papel, religou a
  /// impressora ou corrigiu o cadastro e não tem por que esperar a escada de
  /// retentativa recomeçar do zero. As tentativas anteriores são esquecidas
  /// justamente porque a causa mudou.
  Future<void> retryNow(int id) async {
    await database.execute(
      '''
      UPDATE print_queue
      SET status = 'PENDING', attempts = 0, next_retry_at = NULL,
          lease_owner = NULL, lease_until = NULL, last_error = NULL,
          updated_at = ?
      WHERE id = ? AND status != 'PRINTED'
      ''',
      [DateTime.now().toUtc().toIso8601String(), id],
    );
  }

  /// O operador desistiu deste cupom: ele sai da fila e não sai no papel.
  ///
  /// Mesmo efeito de [forget], nome diferente porque a intenção é outra —
  /// aqui não houve confirmação nenhuma, houve desistência.
  Future<void> discard(int id) => forget(id);

  /// Esvazia a fila: nada do que está esperando vai sair no papel.
  ///
  /// É o descarte um a um aplicado de uma vez, para quando a fila inteira
  /// perdeu o sentido — o caso que motivou isto foi um terminal que trocou de
  /// papel na rede local e acordou com dezenas de cupons herdados esperando.
  /// Descartar trinta cupons um por um não é uma opção para quem tem fila no
  /// balcão.
  ///
  /// O que já saiu no papel (`PRINTED`) não é tocado: aquelas linhas são o
  /// registro de que o cupom saiu, e é o que impede o mesmo trabalho do
  /// servidor de entrar de novo na fila. Devolve quantos cupons saíram.
  Future<int> clearPending({required String scope}) async {
    final row = await database.querySingle(
      "SELECT COUNT(*) AS total FROM print_queue "
      "WHERE scope = ? AND status != 'PRINTED'",
      [scope],
    );
    final total = (row?['total'] as num?)?.toInt() ?? 0;
    if (total == 0) return 0;
    await database.execute(
      "DELETE FROM print_queue WHERE scope = ? AND status != 'PRINTED'",
      [scope],
    );
    return total;
  }

  /// Antecipa as esperas — usado quando a impressora volta a responder.
  Future<void> retryAllNow({required String scope}) async {
    await database.execute(
      '''
      UPDATE print_queue
      SET next_retry_at = NULL, lease_owner = NULL, lease_until = NULL
      WHERE scope = ? AND status = 'PENDING'
      ''',
      [scope],
    );
  }

  /// Situação atual de um trabalho, pelo identificador local.
  Future<PrintJobStatus?> statusOf(String jobId) async {
    final row = await database.querySingle(
      'SELECT status FROM print_queue WHERE job_id = ?',
      [jobId],
    );
    return row == null ? null : PrintJobStatus.parse(row['status']);
  }

  /// Já existe um trabalho nesta fila para este `PrintJob` do servidor?
  Future<bool> containsRemote({
    required String scope,
    required String remoteJobId,
  }) async {
    final row = await database.querySingle(
      'SELECT 1 FROM print_queue WHERE scope = ? AND remote_job_id = ?',
      [scope, remoteJobId],
    );
    return row != null;
  }

  /// Trabalhos que já saíram no papel mas cuja confirmação ao servidor ainda
  /// não foi aceita.
  Future<List<PrintQueueEntry>> awaitingConfirmation({
    required String scope,
  }) async {
    final rows = await database.query(
      '''
      SELECT * FROM print_queue
      WHERE scope = ? AND status = 'PRINTED' AND remote_job_id IS NOT NULL
      ORDER BY id
      LIMIT 50
      ''',
      [scope],
    );
    return rows.map(PrintQueueEntry.fromRow).toList();
  }

  /// O servidor aceitou a confirmação: o trabalho sai da fila.
  Future<void> forget(int id) async {
    await database.execute('DELETE FROM print_queue WHERE id = ?', [id]);
  }

  /// Limpa o que já foi impresso, para a fila não crescer sem fim num
  /// terminal que imprime o dia inteiro.
  ///
  /// Um trabalho do servidor cuja confirmação nunca foi aceita também sai,
  /// mas só depois de bem mais tempo: enquanto ele estiver aqui, a fila de
  /// confirmações fica presa nele e nenhuma outra sobe.
  Future<void> purgeConfirmed({
    required String scope,
    Duration keep = const Duration(hours: 6),
    Duration keepUnconfirmed = const Duration(days: 3),
  }) async {
    final now = DateTime.now().toUtc();
    await database.execute(
      '''
      DELETE FROM print_queue
      WHERE scope = ? AND status = 'PRINTED' AND printed_at < CASE
        WHEN remote_job_id IS NULL THEN ? ELSE ? END
      ''',
      [
        scope,
        now.subtract(keep).toIso8601String(),
        now.subtract(keepUnconfirmed).toIso8601String(),
      ],
    );
  }

  Future<PrintQueueSummary> summary({required String scope}) async {
    final rows = await database.query(
      '''
      SELECT status, COUNT(*) AS total FROM print_queue
      WHERE scope = ? AND status IN ('PENDING', 'PRINTING', 'FAILED')
      GROUP BY status
      ''',
      [scope],
    );
    var pending = 0;
    var failed = 0;
    for (final row in rows) {
      final total = (row['total'] as num?)?.toInt() ?? 0;
      if (PrintJobStatus.parse(row['status']) == PrintJobStatus.failed) {
        failed += total;
      } else {
        pending += total;
      }
    }
    return PrintQueueSummary(pending: pending, failed: failed);
  }

  Future<List<PrintQueueEntry>> entries({
    required String scope,
    bool onlyFailed = false,
    int limit = 100,
  }) async {
    final rows = await database.query(
      '''
      SELECT * FROM print_queue
      WHERE scope = ? ${onlyFailed ? "AND status = 'FAILED'" : "AND status != 'PRINTED'"}
      ORDER BY id
      LIMIT ?
      ''',
      [scope, limit],
    );
    return rows.map(PrintQueueEntry.fromRow).toList();
  }

  static Duration backoffFor(int attempts) {
    final index = min(max(attempts - 1, 0), retryLadder.length - 1);
    return retryLadder[index];
  }
}
