import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'garcom_update_installer.dart';
import 'garcom_update_service.dart';

enum GarcomUpdateBannerPhase {
  hidden,
  available,
  downloading,
  readyToInstall,
  failed,
}

/// Estado da atualização do app do garçom, para o banner em [OrdersPage].
///
/// Fica pronto assim que o app abre (`checkForUpdate` chamado uma vez no
/// `initState` da tela de pedidos) — não há timer nem verificação em
/// segundo plano: o garçom só precisa saber que existe versão nova quando
/// entra no app, não a cada minuto.
class GarcomUpdateController extends ChangeNotifier {
  GarcomUpdateController({GarcomUpdateService? service})
    : _service = service ?? GarcomUpdateService();

  final GarcomUpdateService _service;

  GarcomUpdateBannerPhase phase = GarcomUpdateBannerPhase.hidden;
  GarcomUpdatePackage? _package;
  double? progress;
  String? detail;
  bool _disposed = false;

  Future<void> checkForUpdate() async {
    final status = await _service.check();
    if (_disposed) return;
    if (status.phase != GarcomUpdatePhase.updateAvailable) return;
    _package = status.package;
    _setPhase(GarcomUpdateBannerPhase.available);
  }

  Future<void> downloadAndInstall() async {
    final package = _package;
    if (package == null) return;
    _setPhase(GarcomUpdateBannerPhase.downloading);
    try {
      final destination = await getApplicationDocumentsDirectory();
      final downloaded = await _service.downloadAndVerify(
        package,
        destination,
        onProgress: (received, total) {
          if (_disposed) return;
          progress = total <= 0 ? null : received / total;
          notifyListeners();
        },
      );
      if (_disposed) return;
      _setPhase(GarcomUpdateBannerPhase.readyToInstall);
      await GarcomUpdateInstaller.install(downloaded.file);
      // O Android troca para a tela do instalador aqui; se o garçom voltar
      // sem confirmar (ou cancelar), o banner some mesmo assim — insistir
      // de novo só nesta sessão seria repetitivo, e o próximo abrir do app
      // já checa de novo.
      if (!_disposed) _setPhase(GarcomUpdateBannerPhase.hidden);
    } catch (error) {
      if (_disposed) return;
      _setPhase(
        GarcomUpdateBannerPhase.failed,
        detail: 'Não foi possível baixar a atualização: $error',
      );
    }
  }

  void _setPhase(GarcomUpdateBannerPhase value, {String? detail}) {
    if (_disposed) return;
    phase = value;
    this.detail = detail;
    if (value != GarcomUpdateBannerPhase.downloading) progress = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _service.dispose();
    super.dispose();
  }
}
