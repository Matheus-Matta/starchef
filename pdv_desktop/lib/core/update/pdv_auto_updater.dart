import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../logging/app_logger.dart';
import '../storage/app_paths.dart';
import 'pdv_update_installer.dart';
import 'pdv_update_service.dart';

enum PdvAutoUpdatePhase {
  idle,
  checking,
  downloading,
  preparing,
  restarting,
  upToDate,
  failed,
}

class PdvAutoUpdater extends ChangeNotifier {
  PdvAutoUpdater({
    PdvUpdateService? service,
    PdvUpdateInstaller? installer,
    bool? enabled,
  }) : _service = service ?? PdvUpdateService(),
       _installer = installer ?? PdvUpdateInstaller(),
       enabled = enabled ?? kReleaseMode;

  final PdvUpdateService _service;
  final PdvUpdateInstaller _installer;
  final bool enabled;

  PdvAutoUpdatePhase phase = PdvAutoUpdatePhase.idle;
  PdvUpdateStatus? status;
  double? progress;
  String? detail;
  bool _started = false;
  bool _disposed = false;

  bool get blocksInteraction => switch (phase) {
    PdvAutoUpdatePhase.downloading ||
    PdvAutoUpdatePhase.preparing ||
    PdvAutoUpdatePhase.restarting => true,
    _ => false,
  };

  Future<void> start({required Future<void> Function() closePdv}) async {
    if (_started || !enabled || (!Platform.isWindows && !Platform.isLinux)) {
      return;
    }
    _started = true;
    _setPhase(PdvAutoUpdatePhase.checking);
    try {
      status = await _service.check();
      if (_disposed) return;
      if (status!.phase != PdvUpdatePhase.updateAvailable) {
        _setPhase(
          status!.phase == PdvUpdatePhase.upToDate
              ? PdvAutoUpdatePhase.upToDate
              : PdvAutoUpdatePhase.failed,
          detail: status!.detail,
        );
        return;
      }

      final artifact = status!.artifact!;
      _setPhase(PdvAutoUpdatePhase.downloading);
      final downloads = Directory(
        '${AppPaths.dataDirectory().path}${Platform.pathSeparator}updates'
        '${Platform.pathSeparator}${status!.latestVersion}',
      );
      final downloaded = await _service.downloadAndVerify(
        artifact,
        downloads,
        onProgress: (received, total) {
          if (_disposed) return;
          progress = total <= 0 ? null : received / total;
          notifyListeners();
        },
      );
      if (_disposed) return;
      _setPhase(PdvAutoUpdatePhase.preparing);
      final prepared = await _installer.prepare(
        downloaded,
        status!.latestVersion!,
      );
      if (_disposed) return;
      await _installer.launch(prepared);
      _setPhase(PdvAutoUpdatePhase.restarting);
      AppLogger.instance.info(
        'pdv_update_handoff',
        data: {
          'from': status!.installed?.version,
          'to': status!.latestVersion,
          'artifact': artifact.name,
        },
      );
      await closePdv();
    } catch (error, stackTrace) {
      if (_disposed) return;
      AppLogger.instance.error(
        'pdv_auto_update_failed',
        cause: error,
        stackTrace: stackTrace,
        data: {'version': status?.latestVersion},
      );
      _setPhase(
        PdvAutoUpdatePhase.failed,
        detail: 'A atualização automática falhou. O PDV atual foi mantido.',
      );
    }
  }

  void _setPhase(PdvAutoUpdatePhase value, {String? detail}) {
    if (_disposed) return;
    phase = value;
    this.detail = detail;
    if (value != PdvAutoUpdatePhase.downloading) progress = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _service.dispose();
    super.dispose();
  }
}
