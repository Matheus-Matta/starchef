import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../logging/app_logger.dart';
import 'pdv_troca_de_versao.dart';
import 'pdv_update_installer.dart';
import 'pdv_update_service.dart';
import 'versoes_do_pdv.dart';

part 'pdv_versao_escolhida.dart';

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
    VersaoFixada? versaoFixada,
  }) : _service = service ?? PdvUpdateService(),
       _installer = installer ?? PdvUpdateInstaller(),
       enabled = enabled ?? kReleaseMode,
       _fixada = versaoFixada ?? VersaoFixada.emMemoria();

  final PdvUpdateService _service;
  final PdvUpdateInstaller _installer;
  final bool enabled;
  final VersaoFixada _fixada;

  /// A versão que o operador escolheu manter, ou `null` (atualiza sozinho).
  String? get versaoFixada => _fixada.ler();

  PdvAutoUpdatePhase phase = PdvAutoUpdatePhase.idle;
  PdvUpdateStatus? status;
  double? progress;
  String? detail;
  bool _started = false;
  bool _running = false;
  bool _disposed = false;

  bool get busy => _running;

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
    await _run(closePdv: closePdv, automatico: true);
  }

  /// Repete a consulta e aplica a versão encontrada, mesmo que a tentativa da
  /// abertura já tenha terminado. É o caminho usado pelo botão manual.
  Future<void> checkAndInstall({
    required Future<void> Function() closePdv,
  }) async {
    if (!enabled) {
      _setPhase(
        PdvAutoUpdatePhase.failed,
        detail: 'A atualização só fica ativa no aplicativo instalado.',
      );
      return;
    }
    if (!Platform.isWindows && !Platform.isLinux) {
      _setPhase(
        PdvAutoUpdatePhase.failed,
        detail: 'Atualização não suportada neste sistema operacional.',
      );
      return;
    }
    // Pedir a atualização é desistir da versão fixada.
    await _fixada.gravar(null);
    await _run(closePdv: closePdv);
  }

  Future<void> _run({
    required Future<void> Function() closePdv,
    bool automatico = false,
  }) async {
    if (_running) return;
    _running = true;
    _setPhase(PdvAutoUpdatePhase.checking);
    try {
      status = await _service.check(
        onInstalled: (installed) {
          if (_disposed) return;
          status = PdvUpdateStatus.checking(installed: installed);
          notifyListeners();
        },
      );
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

      // Versão fixada pelo operador: a abertura avisa, mas não troca.
      final fixada = _fixada.ler();
      if (automatico && fixada != null) {
        _setPhase(
          PdvAutoUpdatePhase.idle,
          detail: 'Versão $fixada fixada neste terminal.',
        );
        return;
      }
      await _trocar(status!.artifact!, status!.latestVersion!, closePdv);
    } catch (error, stackTrace) {
      _falhou(error, stackTrace, status?.latestVersion);
    } finally {
      _running = false;
    }
  }

  Future<void> _trocar(
    PdvReleaseArtifact artifact,
    String version,
    Future<void> Function() closePdv,
  ) => trocarDeVersao(
    service: _service,
    installer: _installer,
    artifact: artifact,
    version: version,
    from: status?.installed?.version,
    closePdv: closePdv,
    onFase: (fase) => _setPhase(switch (fase) {
      'downloading' => PdvAutoUpdatePhase.downloading,
      'preparing' => PdvAutoUpdatePhase.preparing,
      _ => PdvAutoUpdatePhase.restarting,
    }),
    onProgress: (received, total) {
      if (_disposed) return;
      progress = total <= 0 ? null : received / total;
      notifyListeners();
    },
  );

  void _falhou(Object error, StackTrace stackTrace, String? version) {
    if (_disposed) return;
    final message = mensagemDaFalha(error);
    AppLogger.instance.error(
      'pdv_auto_update_failed',
      cause: error,
      stackTrace: stackTrace,
      data: {'version': version},
    );
    status = PdvUpdateStatus(
      phase: PdvUpdatePhase.unavailable,
      installed: status?.installed,
      latestVersion: status?.latestVersion,
      releaseUrl: status?.releaseUrl,
      detail: message,
    );
    _setPhase(PdvAutoUpdatePhase.failed, detail: message);
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
