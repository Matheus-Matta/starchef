import 'dart:convert';
import 'dart:io';

import '../storage/app_paths.dart';

/// Dono declarado de um periférico exclusivo.
class PeripheralOwner {
  const PeripheralOwner({
    required this.processId,
    required this.role,
    required this.acquiredAt,
    this.detail,
  });

  final int processId;

  /// Papel de quem reservou: `pdv`, `balanca-rapida`, ...
  final String role;
  final DateTime acquiredAt;
  final String? detail;

  String describe() => detail == null || detail!.isEmpty
      ? '$role (PID $processId)'
      : '$role · $detail (PID $processId)';

  Map<String, dynamic> toJson() => {
    'process_id': processId,
    'role': role,
    'acquired_at': acquiredAt.toIso8601String(),
    if (detail != null) 'detail': detail,
  };

  static PeripheralOwner? fromJson(Map<String, dynamic> json) {
    final processId = (json['process_id'] as num?)?.toInt();
    final acquiredAt = DateTime.tryParse('${json['acquired_at'] ?? ''}');
    if (processId == null || acquiredAt == null) return null;
    return PeripheralOwner(
      processId: processId,
      role: '${json['role'] ?? 'desconhecido'}',
      acquiredAt: acquiredAt,
      detail: json['detail'] as String?,
    );
  }
}

/// Reserva exclusiva de um periférico entre janelas e processos.
///
/// A exclusividade real vem do sistema operacional: uma porta serial só abre
/// uma vez. O que falta é *saber quem* a está usando — sem isso a segunda
/// janela mostra apenas "porta ocupada" e o operador não sabe o que fechar.
///
/// Esta trava usa `RandomAccessFile.lock`, que o sistema libera sozinho quando
/// o processo morre. Assim uma janela encerrada à força não deixa o
/// equipamento bloqueado até o próximo reboot. O descritor com o dono fica em
/// um arquivo separado, legível por quem não conseguiu a trava.
class PeripheralLock {
  PeripheralLock._(this._handle, this._ownerFile, this.resourceId, this.owner);

  final RandomAccessFile _handle;
  final File _ownerFile;
  final String resourceId;
  final PeripheralOwner owner;
  bool _released = false;

  /// Tenta reservar [resourceId]. Devolve `null` se outro processo já o detém.
  static Future<PeripheralLock?> tryAcquire(
    String resourceId, {
    required String role,
    String? detail,
  }) async {
    final lockFile = _fileFor(resourceId, 'lock');
    final ownerFile = _fileFor(resourceId, 'owner');
    await lockFile.parent.create(recursive: true);

    RandomAccessFile? handle;
    try {
      handle = await lockFile.open(mode: FileMode.write);
      await handle.lock(FileLock.exclusive);
    } on FileSystemException {
      await handle?.close();
      return null;
    }

    final owner = PeripheralOwner(
      processId: pid,
      role: role,
      acquiredAt: DateTime.now(),
      detail: detail,
    );
    try {
      await ownerFile.writeAsString(jsonEncode(owner.toJson()), flush: true);
    } catch (_) {
      // O descritor é apenas informativo; a trava já está garantida.
    }
    return PeripheralLock._(handle, ownerFile, resourceId, owner);
  }

  /// Fila justa (FIFO) sobre a mesma trava de [tryAcquire].
  ///
  /// [tryAcquire] resolve na hora — o que a tela de configuração precisa pra
  /// dizer "reservada por fulano" sem esperar. Impressão é diferente: vários
  /// trabalhos curtos disputam a mesma porta o dia inteiro (o processo da
  /// Balança Rápida e o PDV principal, cada um com seus próprios trabalhos),
  /// e um retry otimista pode deixar quem chegou primeiro esperando mais que
  /// quem chegou depois, só por sorte no instante de cada tentativa.
  ///
  /// Cada chamador grava um bilhete com a hora de chegada (arquivo, não uma
  /// fila em memória — o outro processo precisa enxergá-lo) e só tenta a
  /// trava de verdade quando é o bilhete mais antigo ainda vivo. O polling é
  /// só para notar a vez chegar; reage em [pollInterval], bem mais rápido que
  /// esperar todo o intervalo entre tentativas otimistas.
  static Future<PeripheralLock?> acquireQueued(
    String resourceId, {
    required String role,
    String? detail,
    Duration timeout = const Duration(seconds: 4),
    Duration pollInterval = const Duration(milliseconds: 30),
    Duration ticketTtl = const Duration(seconds: 10),
  }) async {
    final ticketsDir = _ticketsDirFor(resourceId);
    await ticketsDir.create(recursive: true);
    final ticketId =
        '${DateTime.now().microsecondsSinceEpoch}-$pid-${_nextTicketSequence()}';
    final ticketFile = File(
      '${ticketsDir.path}${Platform.pathSeparator}$ticketId',
    );
    await ticketFile.writeAsString('$pid', flush: true);

    final deadline = DateTime.now().add(timeout);
    try {
      while (true) {
        if (await _isFrontOfQueue(ticketsDir, ticketId, ticketTtl)) {
          final lock = await tryAcquire(resourceId, role: role, detail: detail);
          if (lock != null) return lock;
          // Outro processo pode ter conseguido a trava fora desta fila (ex.:
          // via tryAcquire direto). Continua esperando a vez em vez de
          // desistir na primeira coincidência.
        }
        if (DateTime.now().isAfter(deadline)) return null;
        await Future<void>.delayed(pollInterval);
      }
    } finally {
      try {
        if (await ticketFile.exists()) await ticketFile.delete();
      } catch (_) {
        // Limpeza é conveniência; um bilhete órfão expira sozinho pelo TTL.
      }
    }
  }

  static int _ticketSequence = 0;

  /// Sequência incremental só para desempatar bilhetes emitidos no mesmo
  /// microssegundo por este processo — seguro porque roda entre dois
  /// `await`, sem concorrência dentro do isolate.
  static int _nextTicketSequence() => _ticketSequence++;

  /// O bilhete de quem chama é o mais antigo entre os ainda vivos?
  ///
  /// Bilhetes mais velhos que [ticketTtl] são tratados como abandonados (o
  /// processo que os criou caiu antes de limpar) e removidos ao serem vistos
  /// — sem isso, um processo morto travaria a fila para sempre.
  static Future<bool> _isFrontOfQueue(
    Directory ticketsDir,
    String myTicketId,
    Duration ticketTtl,
  ) async {
    final now = DateTime.now();
    List<FileSystemEntity> entries;
    try {
      entries = await ticketsDir.list().toList();
    } catch (_) {
      return true; // Sem visibilidade dos concorrentes, segue e deixa o
      // próprio `tryAcquire` decidir.
    }
    int? oldestArrival;
    String? oldestId;
    for (final entry in entries) {
      if (entry is! File) continue;
      final name = entry.uri.pathSegments.last;
      final arrival = int.tryParse(name.split('-').first);
      if (arrival == null) continue;
      DateTime modified;
      try {
        modified = (await entry.stat()).modified;
      } catch (_) {
        continue; // Sumiu entre o list() e o stat(): não conta mais.
      }
      if (now.difference(modified) > ticketTtl) {
        try {
          await entry.delete();
        } catch (_) {}
        continue;
      }
      if (oldestArrival == null || arrival < oldestArrival) {
        oldestArrival = arrival;
        oldestId = name;
      }
    }
    return oldestId == null || oldestId == myTicketId;
  }

  static Directory _ticketsDirFor(String resourceId) {
    final safe = _safeName(resourceId);
    return Directory(
      AppPaths.dataFile(
        'locks${Platform.pathSeparator}$safe.waiting',
      ).path,
    );
  }

  /// Lê quem declarou a posse, mesmo sem conseguir a trava.
  static Future<PeripheralOwner?> currentOwner(String resourceId) async {
    try {
      final file = _fileFor(resourceId, 'owner');
      if (!await file.exists()) return null;
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is! Map) return null;
      return PeripheralOwner.fromJson(Map<String, dynamic>.from(decoded));
    } catch (_) {
      return null;
    }
  }

  Future<void> release() async {
    if (_released) return;
    _released = true;
    try {
      await _handle.unlock();
    } catch (_) {
      // Uma trava já liberada pelo sistema não é um erro para o chamador.
    }
    try {
      await _handle.close();
    } catch (_) {}
    try {
      if (await _ownerFile.exists()) await _ownerFile.delete();
    } catch (_) {}
  }

  static String _safeName(String resourceId) {
    final safe = resourceId
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
    return safe.isEmpty ? 'peripheral' : safe;
  }

  static File _fileFor(String resourceId, String extension) {
    final safe = _safeName(resourceId);
    return AppPaths.dataFile(
      'locks${Platform.pathSeparator}$safe'
      '.$extension',
    );
  }
}
