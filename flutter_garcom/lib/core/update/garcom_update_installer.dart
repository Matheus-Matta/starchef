import 'dart:io';

import 'package:open_filex/open_filex.dart';

/// Abre o instalador nativo do Android por cima do APK baixado.
///
/// `REQUEST_INSTALL_PACKAGES` (AndroidManifest) autoriza este app
/// especificamente a disparar instalação; se o usuário nunca liberou
/// "Instalar apps desconhecidos" para o StarChef Garçom, o próprio Android
/// mostra essa tela de permissão antes do instalador — não há como pular
/// isso por código, é uma decisão do usuário.
abstract final class GarcomUpdateInstaller {
  static Future<void> install(File apk) async {
    final result = await OpenFilex.open(
      apk.path,
      type: 'application/vnd.android.package-archive',
    );
    if (result.type != ResultType.done) {
      throw StateError(result.message);
    }
  }
}
