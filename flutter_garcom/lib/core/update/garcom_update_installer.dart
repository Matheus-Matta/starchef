import 'dart:io';

import 'package:open_filex/open_filex.dart';
import 'package:permission_handler/permission_handler.dart';

/// Recusa da própria instalação, com o motivo em linguagem de operador.
class InstallNotAllowed implements Exception {
  const InstallNotAllowed(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Abre o instalador nativo do Android por cima do APK baixado.
///
/// `REQUEST_INSTALL_PACKAGES` (AndroidManifest) autoriza este app a disparar
/// uma instalação, mas quem decide é o dono do aparelho, em
/// *Instalar apps desconhecidos*. Não há como pular isso por código.
///
/// O que dá para fazer — e é o que mudou aqui — é perguntar na hora CERTA.
/// Antes o app baixava 69 MB e só então disparava o instalador; sem a
/// permissão, o Android interrompia no fim, o operador voltava sem entender, e
/// o download inteiro era repetido na próxima tentativa. Agora a permissão é
/// verificada antes de baixar qualquer byte, e quando falta o operador é levado
/// direto à tela certa — já filtrada por este app, não à lista geral de
/// aplicativos do sistema.
///
/// Vale lembrar: a permissão é por instalação. Desinstalar e instalar de novo
/// (como acontece ao trocar a chave de assinatura) zera a concessão, e ela
/// precisa ser dada mais uma vez.
abstract final class GarcomUpdateInstaller {
  /// O aparelho autoriza este app a instalar pacotes?
  static Future<bool> get allowed async =>
      !Platform.isAndroid || await Permission.requestInstallPackages.isGranted;

  /// Pede a permissão, abrindo a tela do sistema quando necessário.
  ///
  /// Devolve `true` se, ao fim, a instalação está liberada.
  static Future<bool> ensureAllowed() async {
    if (!Platform.isAndroid) return true;
    final status = await Permission.requestInstallPackages.request();
    if (status.isGranted) return true;
    // Negada de forma permanente, o pedido acima não abre mais nada: só as
    // configurações do app resolvem, e é para lá que o operador vai.
    if (status.isPermanentlyDenied) await openAppSettings();
    return Permission.requestInstallPackages.isGranted;
  }

  static Future<void> install(File apk) async {
    if (!await allowed) {
      throw const InstallNotAllowed(
        'O aparelho não autorizou o StarChef Garçom a instalar aplicativos. '
        'Libere em Configurações → Instalar apps desconhecidos.',
      );
    }
    final result = await OpenFilex.open(
      apk.path,
      type: 'application/vnd.android.package-archive',
    );
    if (result.type != ResultType.done) {
      throw StateError(result.message);
    }
  }
}
