import 'package:flutter/services.dart';

/// A ponte com o Android para instalar um APK.
///
/// NO ANDROID NÃO EXISTE TROCA DE PASTA com rollback, como no PDV desktop: quem
/// instala é o instalador do sistema, e ele pede a confirmação da pessoa. O app
/// entrega o arquivo e perde o controle ali — por isso não existe "atualizando"
/// como estado nosso, só "baixado e entregue".
///
/// A PERMISSÃO É O PONTO QUE MAIS TRAVA NA PRÁTICA. Instalar de fora da Play
/// Store exige que o aparelho autorize ESTE app a instalar pacotes, e sem isso o
/// instalador abre e fecha sem dizer nada. Por isso `canInstall` existe: dá para
/// levar o garçom à tela certa em vez de deixá-lo achando que o download falhou.
class MobileUpdateInstaller {
  const MobileUpdateInstaller({MethodChannel? channel})
    : _channel = channel ?? const MethodChannel(_nome);

  static const _nome = 'br.com.starchef.pdv_mobile/apk_install';

  final MethodChannel _channel;

  /// A arquitetura principal do aparelho ("arm64-v8a"), ou vazio.
  ///
  /// Vazio faz o serviço cair no APK universal, que instala em qualquer um — a
  /// falha aqui custa banda, nunca a atualização.
  Future<String> abi() async {
    try {
      return await _channel.invokeMethod<String>('abi') ?? '';
    } on PlatformException {
      return '';
    } on MissingPluginException {
      return '';
    }
  }

  /// O aparelho autoriza este app a instalar pacotes?
  Future<bool> canInstall() async {
    try {
      return await _channel.invokeMethod<bool>('canInstall') ?? false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  /// Abre a tela do Android onde a autorização é concedida.
  Future<void> openInstallPermission() async {
    try {
      await _channel.invokeMethod<void>('openInstallPermission');
    } on PlatformException {
      // Aparelho sem essa tela (fabricante que a esconde): o aviso na interface
      // já explica o caminho manual, e estourar aqui não ajudaria ninguém.
    } on MissingPluginException {
      // ignore: nada a abrir fora do Android.
    }
  }

  /// Entrega o APK ao instalador do sistema.
  ///
  /// Devolve `false` quando o Android recusou receber. Não devolve sucesso da
  /// INSTALAÇÃO: quem decide isso é a pessoa, na tela do sistema, depois.
  Future<bool> install(String caminho) async {
    try {
      return await _channel.invokeMethod<bool>('install', {'path': caminho}) ?? false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }
}
