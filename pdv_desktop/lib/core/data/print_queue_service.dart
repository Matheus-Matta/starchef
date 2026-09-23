import 'dart:convert';
import 'dart:io';
import 'dart:math';

import '../storage/app_paths.dart';
import 'local_id.dart';

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
    this.scope = '',
    this.remoteJobId,
    this.barcode,
    this.qr,
    this.openCashDrawer = false,
    this.nextRetryAt,
    this.printedAt,
    this.leaseOwner,
    this.leaseUntil,
    this.lastError,
  });

  final int id;

  /// Identificador do trabalho neste terminal.
  final String jobId;

  /// Identificador do `PrintJob` no servidor, quando ele veio de lá. É o que
  /// permite confirmar a impressão depois e o que impede o mesmo cupom de
  /// entrar duas vezes na fila.
  final String? remoteJobId;

  final String scope;
  final String printerId;

  /// Cópia do cadastro da impressora no momento em que o cupom entrou. Se o
  /// cadastro mudar entre a fila e o papel, o trabalho ainda sai no
  /// equipamento para o qual foi montado.
  final Map<String, dynamic> printer;

  final String jobType;
  final String content;
  final String? barcode;
  final String? qr;

  /// O cupom leva junto o pulso da gaveta quando finalmente sair.
  ///
  /// Guardado na fila porque a gaveta pertence ao trabalho, não ao instante:
  /// uma venda em dinheiro que esperou a impressora voltar continua sendo uma
  /// venda em dinheiro quando o papel sai.
  final bool openCashDrawer;

  final PrintJobStatus status;
  final int attempts;
  final DateTime createdAt;
  final DateTime? nextRetryAt;
  final DateTime? printedAt;
  final String? leaseOwner;
  final DateTime? leaseUntil;
  final String? lastError;

  PrintQueueEntry copyWith({
    PrintJobStatus? status,
    int? attempts,
    DateTime? nextRetryAt,
    DateTime? printedAt,
    String? leaseOwner,
    DateTime? leaseUntil,
    String? lastError,
    bool clearNextRetryAt = false,
    bool clearLease = false,
    bool clearError = false,
  }) => PrintQueueEntry(
    id: id,
    jobId: jobId,
    scope: scope,
    remoteJobId: remoteJobId,
    printerId: printerId,
    printer: printer,
    jobType: jobType,
    content: content,
    barcode: barcode,
    qr: qr,
    openCashDrawer: openCashDrawer,
    status: status ?? this.status,
    attempts: attempts ?? this.attempts,
    createdAt: createdAt,
    nextRetryAt: clearNextRetryAt ? null : (nextRetryAt ?? this.nextRetryAt),
    printedAt: printedAt ?? this.printedAt,
    leaseOwner: clearLease ? null : (leaseOwner ?? this.leaseOwner),
    leaseUntil: clearLease ? null : (leaseUntil ?? this.leaseUntil),
    lastError: clearError ? null : (lastError ?? this.lastError),
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'job_id': jobId,
    'scope': scope,
    'remote_job_id': remoteJobId,
    'printer_id': printerId,
    'printer': printer,
    'job_type': jobType,
    'content': content,
    'barcode': barcode,
    'qr': qr,
    'open_cash_drawer': openCashDrawer,
    'status': status.code,
    'attempts': attempts,
    'created_at': createdAt.toIso8601String(),
    'next_retry_at': nextRetryAt?.toIso8601String(),
    'printed_at': printedAt?.toIso8601String(),
    'lease_owner': leaseOwner,
    'lease_until': leaseUntil?.toIso8601String(),
    'last_error': lastError,
  };

  static PrintQueueEntry fromJson(Map<String, dynamic> row) {
    final printer = row['printer'];
    return PrintQueueEntry(
      id: (row['id'] as num?)?.toInt() ?? 0,
      jobId: '${row['job_id']}',
      scope: '${row['scope'] ?? ''}',
      remoteJobId: row['remote_job_id'] as String?,
      printerId: '${row['printer_id'] ?? ''}',
      printer: printer is Map
          ? Map<String, dynamic>.from(printer)
          : <String, dynamic>{},
      jobType: '${row['job_type']}',
      content: '${row['content']}',
      barcode: row['barcode'] as String?,
      qr: row['qr'] as String?,
      // Linhas gravadas antes deste campo existir não abrem gaveta nenhuma.
      openCashDrawer: row['open_cash_drawer'] == true,
      status: PrintJobStatus.parse(row['status']),
      attempts: (row['attempts'] as num?)?.toInt() ?? 0,
      createdAt:
          DateTime.tryParse('${row['created_at']}')?.toUtc() ??
          DateTime.now().toUtc(),
      nextRetryAt: DateTime.tryParse('${row['next_retry_at'] ?? ''}')?.toUtc(),
      printedAt: DateTime.tryParse('${row['printed_at'] ?? ''}')?.toUtc(),
      leaseOwner: row['lease_owner'] as String?,
      leaseUntil: DateTime.tryParse('${row['lease_until'] ?? ''}')?.toUtc(),
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

/// **A fila de impressão é do terminal, não do servidor.**
///
/// O backend monta o documento (é ele quem sabe o preço, o imposto e o
/// layout) e o PDV é quem põe no papel: é ele que enxerga a impressora USB do
/// balcão. Entre uma coisa e outra existe o mundo físico — papel acabando,
/// cabo solto, equipamento desligado — e é por isso que esta fila existe,
/// mesmo num terminal que só opera conectado. Sem ela, uma impressora sem
/// papel perderia o cupom em silêncio.
///
/// Ela guarda **apenas trabalho de impressora**: conteúdo já renderizado,
/// destino e o histórico de tentativas. Nenhum dado de venda mora aqui.
///
/// O arquivo é compartilhado com o processo da Balança Rápida, que é uma
/// segunda janela em um processo separado e tem impressora própria. Por isso
/// toda leitura-modificação-escrita passa por um lock de arquivo do sistema
/// operacional: sem ele, os dois processos pegariam o mesmo cupom e o papel
/// sairia duas vezes.
class PrintQueueService {
  PrintQueueService({File? file, File? lockFile, String? leaseOwner})
    : _file = file ?? AppPaths.dataFile(_fileName),
      _lockFile = lockFile ?? AppPaths.dataFile('$_fileName.lock'),
      _leaseOwner = leaseOwner ?? 'spooler-${LocalId.uuid()}';

  static const _fileName = 'print_queue.json';

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
  /// desinstalada, endereço trocado, setor sem equipamento) giraria até
  /// expirar — centenas de tentativas, cada uma custando um tempo limite
  /// inteiro e atrasando os cupons bons atrás dele. Quinze cobrem com folga
  /// uma troca de papel ou um religar de impressora; depois disso o cupom fica
  /// visível na tela da fila, onde o operador decide entre tentar de novo
  /// (o que zera esta contagem) e descartar.
  static int get maximumAttempts => retryLadder.length;

  /// Depois disso o cupom não interessa mais a ninguém: uma comanda de ontem
  /// saindo hoje confunde a cozinha mais do que ajuda.
  static const expiresAfter = Duration(hours: 12);

  static const leaseDuration = Duration(seconds: 60);

  final File _file;
  final File _lockFile;
  final String _leaseOwner;

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
    return _read(
      (state) => state.printedDocuments.containsKey('$scope|$dedupeKey'),
    );
  }

  /// Registra que este documento saiu no papel neste terminal.
  Future<void> markDocumentPrinted({
    required String scope,
    required String dedupeKey,
  }) async {
    if (dedupeKey.isEmpty) return;
    await _mutate((state) {
      state.printedDocuments['$scope|$dedupeKey'] = DateTime.now()
          .toUtc()
          .toIso8601String();
    });
  }

  /// Coloca um cupom na fila. Repetir a mesma origem não duplica o papel.
  ///
  /// [remoteJobId] identifica o `PrintJob` do servidor: enquanto o
  /// `mark-printed` não é confirmado, o mesmo trabalho volta a aparecer na
  /// consulta, e sem esta chave ele entraria de novo na fila.
  /// [heldReason] entra o cupom **parado**, esperando uma decisão de quem está
  /// no balcão em vez de ir direto para a impressora.
  Future<String> enqueue({
    required String scope,
    required Map<String, dynamic> printer,
    required String jobType,
    required String content,
    String? jobId,
    String? remoteJobId,
    String? barcode,
    String? qr,
    bool openCashDrawer = false,
    String? heldReason,
  }) async {
    final id = jobId ?? remoteJobId ?? LocalId.uuid();
    await _mutate((state) {
      // ON CONFLICT(job_id) DO NOTHING: o mesmo gesto repetido não vira
      // segundo papel.
      if (state.entries.any((entry) => entry.jobId == id)) return;
      final now = DateTime.now().toUtc();
      state.sequence += 1;
      state.entries.add(
        PrintQueueEntry(
          id: state.sequence,
          jobId: id,
          scope: scope,
          remoteJobId: remoteJobId,
          printerId: '${printer['id'] ?? ''}',
          printer: printer,
          jobType: jobType,
          content: content,
          barcode: barcode,
          qr: qr,
          openCashDrawer: openCashDrawer,
          status: heldReason == null
              ? PrintJobStatus.pending
              : PrintJobStatus.failed,
          attempts: 0,
          createdAt: now,
          lastError: heldReason,
        ),
      );
    });
    return id;
  }

  /// Próximo cupom a sair, já reservado para este processo.
  ///
  /// A reserva importa porque o PDV e a janela da Balança Rápida compartilham
  /// o arquivo: sem ela, os dois pegariam o mesmo trabalho e o papel sairia
  /// duas vezes.
  Future<PrintQueueEntry?> claimNext({required String scope}) async {
    PrintQueueEntry? claimed;
    await _mutate((state) {
      final now = DateTime.now().toUtc();
      final index = state.entries.indexWhere(
        (entry) =>
            entry.scope == scope &&
            (entry.status == PrintJobStatus.pending ||
                entry.status == PrintJobStatus.printing) &&
            (entry.nextRetryAt == null || !entry.nextRetryAt!.isAfter(now)) &&
            (entry.leaseUntil == null || !entry.leaseUntil!.isAfter(now)),
      );
      if (index < 0) return;
      final entry = state.entries[index];
      if (now.difference(entry.createdAt) > expiresAfter) {
        state.entries[index] = entry.copyWith(
          status: PrintJobStatus.failed,
          lastError: 'Trabalho expirado sem conseguir imprimir.',
          clearLease: true,
        );
        return;
      }
      claimed = entry.copyWith(
        status: PrintJobStatus.printing,
        leaseOwner: _leaseOwner,
        leaseUntil: now.add(leaseDuration),
      );
      state.entries[index] = claimed!;
    });
    return claimed;
  }

  /// O papel saiu.
  Future<void> markPrinted(int id) => _update(
    id,
    (entry) => entry.copyWith(
      status: PrintJobStatus.printed,
      printedAt: DateTime.now().toUtc(),
      clearError: true,
      clearLease: true,
    ),
  );

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
    final nextRetryAt = DateTime.now().toUtc().add(backoffFor(attempts));
    await _update(
      id,
      (entry) => entry.copyWith(
        status: PrintJobStatus.pending,
        attempts: attempts,
        nextRetryAt: nextRetryAt,
        lastError: error,
        clearLease: true,
      ),
    );
    return PrintRetryOutcome(
      attempts: attempts,
      nextRetryAt: nextRetryAt,
      exhausted: false,
    );
  }

  /// Erro que nenhuma repetição resolve: trabalho sem conteúdo, impressora
  /// sem endereço configurado.
  Future<void> markFailed(int id, {required String error, int? attempts}) =>
      _update(
        id,
        (entry) => entry.copyWith(
          status: PrintJobStatus.failed,
          attempts: attempts ?? entry.attempts,
          lastError: error,
          clearNextRetryAt: true,
          clearLease: true,
        ),
      );

  /// Recoloca um trabalho recusado na fila, depois que o operador resolveu a
  /// causa (trocou o papel, religou a impressora).
  Future<void> retryFailed(int id) => _update(
    id,
    (entry) => entry.status != PrintJobStatus.failed
        ? entry
        : entry.copyWith(
            status: PrintJobStatus.pending,
            attempts: 0,
            clearNextRetryAt: true,
            clearError: true,
          ),
  );

  /// Antecipa a espera de UM trabalho, ou traz de volta um recusado.
  ///
  /// É o "tentar agora" da tela da fila: o operador trocou o papel, religou a
  /// impressora ou corrigiu o cadastro e não tem por que esperar a escada de
  /// retentativa recomeçar do zero. As tentativas anteriores são esquecidas
  /// justamente porque a causa mudou.
  Future<void> retryNow(int id) => _update(
    id,
    (entry) => entry.status == PrintJobStatus.printed
        ? entry
        : entry.copyWith(
            status: PrintJobStatus.pending,
            attempts: 0,
            clearNextRetryAt: true,
            clearError: true,
            clearLease: true,
          ),
  );

  /// O operador desistiu deste cupom: ele sai da fila e não sai no papel.
  ///
  /// Mesmo efeito de [forget], nome diferente porque a intenção é outra —
  /// aqui não houve confirmação nenhuma, houve desistência.
  Future<void> discard(int id) => forget(id);

  /// Esvazia a fila: nada do que está esperando vai sair no papel.
  ///
  /// O que já saiu no papel (`PRINTED`) não é tocado: aquelas linhas são o
  /// registro de que o cupom saiu, e é o que impede o mesmo trabalho do
  /// servidor de entrar de novo na fila. Devolve quantos cupons saíram.
  Future<int> clearPending({required String scope}) async {
    var removed = 0;
    await _mutate((state) {
      final before = state.entries.length;
      state.entries.removeWhere(
        (entry) =>
            entry.scope == scope && entry.status != PrintJobStatus.printed,
      );
      removed = before - state.entries.length;
    });
    return removed;
  }

  /// Antecipa as esperas — usado quando a impressora volta a responder.
  Future<void> retryAllNow({required String scope}) => _mutate((state) {
    for (var index = 0; index < state.entries.length; index += 1) {
      final entry = state.entries[index];
      if (entry.scope != scope || entry.status != PrintJobStatus.pending) {
        continue;
      }
      state.entries[index] = entry.copyWith(
        clearNextRetryAt: true,
        clearLease: true,
      );
    }
  });

  /// Situação atual de um trabalho, pelo identificador local.
  Future<PrintJobStatus?> statusOf(String jobId) => _read((state) {
    for (final entry in state.entries) {
      if (entry.jobId == jobId) return entry.status;
    }
    return null;
  });

  /// Já existe um trabalho nesta fila para este `PrintJob` do servidor?
  Future<bool> containsRemote({
    required String scope,
    required String remoteJobId,
  }) => _read(
    (state) => state.entries.any(
      (entry) => entry.scope == scope && entry.remoteJobId == remoteJobId,
    ),
  );

  /// Trabalhos que já saíram no papel mas cuja confirmação ao servidor ainda
  /// não foi aceita.
  Future<List<PrintQueueEntry>> awaitingConfirmation({
    required String scope,
  }) => _read(
    (state) => state.entries
        .where(
          (entry) =>
              entry.scope == scope &&
              entry.status == PrintJobStatus.printed &&
              entry.remoteJobId != null,
        )
        .take(50)
        .toList(),
  );

  /// O servidor aceitou a confirmação: o trabalho sai da fila.
  Future<void> forget(int id) =>
      _mutate((state) => state.entries.removeWhere((entry) => entry.id == id));

  /// Limpa o que já foi impresso, para a fila não crescer sem fim num terminal
  /// que imprime o dia inteiro.
  ///
  /// Um trabalho do servidor cuja confirmação nunca foi aceita também sai, mas
  /// só depois de bem mais tempo: enquanto ele estiver aqui, a fila de
  /// confirmações fica presa nele e nenhuma outra sobe.
  Future<void> purgeConfirmed({
    required String scope,
    Duration keep = const Duration(hours: 6),
    Duration keepUnconfirmed = const Duration(days: 3),
  }) {
    final now = DateTime.now().toUtc();
    return _mutate((state) {
      state.entries.removeWhere((entry) {
        if (entry.scope != scope) return false;
        if (entry.status != PrintJobStatus.printed) return false;
        final printedAt = entry.printedAt;
        if (printedAt == null) return false;
        final limit = entry.remoteJobId == null
            ? now.subtract(keep)
            : now.subtract(keepUnconfirmed);
        return printedAt.isBefore(limit);
      });
      // Marcas de documento impresso não podem crescer para sempre: o que
      // importa é impedir a segunda via no mesmo dia, não guardar histórico.
      state.printedDocuments.removeWhere((_, raw) {
        final at = DateTime.tryParse(raw);
        return at != null && at.isBefore(now.subtract(const Duration(days: 7)));
      });
    });
  }

  Future<PrintQueueSummary> summary({required String scope}) => _read((state) {
    var pending = 0;
    var failed = 0;
    for (final entry in state.entries) {
      if (entry.scope != scope) continue;
      switch (entry.status) {
        case PrintJobStatus.failed:
          failed += 1;
        case PrintJobStatus.pending:
        case PrintJobStatus.printing:
          pending += 1;
        case PrintJobStatus.printed:
          break;
      }
    }
    return PrintQueueSummary(pending: pending, failed: failed);
  });

  Future<List<PrintQueueEntry>> entries({
    required String scope,
    bool onlyFailed = false,
    int limit = 100,
  }) => _read(
    (state) => state.entries
        .where(
          (entry) =>
              entry.scope == scope &&
              (onlyFailed
                  ? entry.status == PrintJobStatus.failed
                  : entry.status != PrintJobStatus.printed),
        )
        .take(limit)
        .toList(),
  );

  static Duration backoffFor(int attempts) {
    final index = min(max(attempts - 1, 0), retryLadder.length - 1);
    return retryLadder[index];
  }

  Future<void> _update(
    int id,
    PrintQueueEntry Function(PrintQueueEntry entry) change,
  ) => _mutate((state) {
    final index = state.entries.indexWhere((entry) => entry.id == id);
    if (index < 0) return;
    state.entries[index] = change(state.entries[index]);
  });

  // ---------------------------------------------------------------------
  // Arquivo
  // ---------------------------------------------------------------------

  Future<T> _read<T>(T Function(_QueueState state) reader) =>
      _withLock(exclusive: false, action: reader);

  Future<void> _mutate(void Function(_QueueState state) change) =>
      _withLock<void>(exclusive: true, action: change);

  /// Serializa o acesso ao arquivo entre processos.
  ///
  /// O lock é de um arquivo separado (`.lock`) e não do próprio JSON: a
  /// gravação troca o arquivo de dados por um `rename` atômico, e um lock
  /// preso ao inode antigo não protegeria nada depois da troca.
  Future<T> _withLock<T>({
    required bool exclusive,
    required T Function(_QueueState state) action,
  }) async {
    RandomAccessFile? handle;
    try {
      await _lockFile.parent.create(recursive: true);
      handle = await _lockFile.open(mode: FileMode.write);
      await handle.lock(
        exclusive ? FileLock.blockingExclusive : FileLock.blockingShared,
      );
    } catch (_) {
      // Sistema de arquivos sem suporte a lock (um volume de rede, por
      // exemplo). Um cupom duplicado é melhor do que um PDV que não imprime:
      // segue sem exclusão mútua.
      await handle?.close();
      handle = null;
    }
    try {
      final state = await _load();
      final result = action(state);
      if (exclusive) await _flush(state);
      return result;
    } finally {
      if (handle != null) {
        try {
          await handle.unlock();
        } catch (_) {}
        await handle.close();
      }
    }
  }

  Future<_QueueState> _load() async {
    try {
      if (!await _file.exists()) return _QueueState.empty();
      final decoded = jsonDecode(await _file.readAsString());
      if (decoded is! Map) return _QueueState.empty();
      return _QueueState.fromJson(Map<String, dynamic>.from(decoded));
    } catch (_) {
      // JSON truncado por uma queda de energia no meio da escrita. A fila
      // recomeça vazia — nenhum cupom sai duas vezes por causa disso, e o PDV
      // abre.
      return _QueueState.empty();
    }
  }

  Future<void> _flush(_QueueState state) async {
    await _file.parent.create(recursive: true);
    final temporary = File('${_file.path}.tmp');
    await temporary.writeAsString(jsonEncode(state.toJson()), flush: true);
    await temporary.rename(_file.path);
  }
}

class _QueueState {
  _QueueState({
    required this.sequence,
    required this.entries,
    required this.printedDocuments,
  });

  factory _QueueState.empty() => _QueueState(
    sequence: 0,
    entries: <PrintQueueEntry>[],
    printedDocuments: <String, String>{},
  );

  factory _QueueState.fromJson(Map<String, dynamic> raw) {
    final entries = (raw['entries'] as List? ?? const [])
        .whereType<Map>()
        .map((row) => PrintQueueEntry.fromJson(Map<String, dynamic>.from(row)))
        .toList();
    final documents = <String, String>{};
    final rawDocuments = raw['printed_documents'];
    if (rawDocuments is Map) {
      rawDocuments.forEach((key, value) => documents['$key'] = '$value');
    }
    return _QueueState(
      sequence: (raw['sequence'] as num?)?.toInt() ?? 0,
      entries: entries,
      printedDocuments: documents,
    );
  }

  int sequence;
  final List<PrintQueueEntry> entries;
  final Map<String, String> printedDocuments;

  Map<String, dynamic> toJson() => {
    'sequence': sequence,
    'entries': entries.map((entry) => entry.toJson()).toList(),
    'printed_documents': printedDocuments,
  };
}
