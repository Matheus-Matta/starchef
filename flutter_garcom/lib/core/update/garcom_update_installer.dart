import 'dart:io';

import 'package:flutter/services.dart';
import 'package:open_filex/open_filex.dart';

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
/// Antes o app baixava dezenas de MB e só então disparava o instalador; sem a
/// permissão, o Android interrompia no fim, o operador voltava sem entender, e
/// o download inteiro era repetido na próxima tentativa. Agora a permissão é
/// verificada antes de baixar qualquer byte, e quando falta o operador é levado
/// direto à tela certa — já filtrada por este app, não à lista geral do
/// sistema.
///
/// A conversa com o Android é um [MethodChannel] de duas chamadas, atendido em
/// `MainActivity.kt`. Um plugin de permissões faria o mesmo trazendo seis
/// dependências e exigindo um `compileSdk` acima do que o Android Gradle Plugin
/// recomenda — foi assim que o build de release quebrou uma vez.
///
/// Vale lembrar: a permissão é por instalação. Desinstalar e instalar de novo
/// (como acontece ao trocar a chave de assinatura) zera a concessão, e ela
/// precisa ser dada mais uma vez.
abstract final class GarcomUpdateInstaller {
  static const _channel = MethodChannel('br.com.starchef.garcom/install');

  /// O aparelho autoriza este app a instalar pacotes?
  ///
  /// Fora do Android não há essa noção, e a resposta é sim: o teste roda no
  /// desktop e não pode depender de um canal que ninguém atende.
  static Future<bool> get allowed async {
    if (!Platform.isAndroid) return true;
    try {
      return await _channel.invokeMethod<bool>('canInstall') ?? false;
    } on PlatformException {
      // Sem resposta do lado nativo, seguir em frente é melhor do que travar:
      // o pior caso vira o comportamento antigo, com o Android perguntando no
      // fim.
      return true;
    } on MissingPluginException {
      return true;
    }
  }

  /// Leva o operador à tela de autorização, quando ela falta.
  ///
  /// Devolve `true` se, ao voltar, a instalação está liberada. O Android não
  /// avisa quando o operador concede, então a checagem é refeita — se ele
  /// liberou, a próxima tentativa já passa.
  static Future<bool> ensureAllowed() async {
    if (await allowed) return true;
    try {
      await _channel.invokeMethod<bool>('openSettings');
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
    return allowed;
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
