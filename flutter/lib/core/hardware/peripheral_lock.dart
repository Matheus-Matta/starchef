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

  static File _fileFor(String resourceId, String extension) {
    final safe = resourceId
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
    return AppPaths.dataFile(
      'locks${Platform.pathSeparator}${safe.isEmpty ? 'peripheral' : safe}'
      '.$extension',
    );
  }
}
