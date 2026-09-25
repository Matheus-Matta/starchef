import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';

import 'mobile_release.dart';
import 'mobile_update_installer.dart';

/// `latest-mobile.json`, e NÃO `latest-desktop.json` nem `latest.json`.
///
/// Três manifestos convivem no projeto: o do PDV Windows/Linux, o deste app e o
/// da linhagem 1.8.x do PDV offline, que segue em produção em outras branches.
/// Ler o errado faria o celular do garçom baixar um ZIP de Windows.
const _manifestoPadrao =
    'https://github.com/Matheus-Matta/starchef/releases/latest/download/latest-mobile.json';

/// O Actions redefine isto com o repositório do build, para um fork não apontar
/// para o repositório-base.
const urlDoManifestoMovel = String.fromEnvironment(
  'PDV_MOBILE_MANIFEST_URL',
  defaultValue: _manifestoPadrao,
);

enum UpdatePhase { checking, upToDate, available, unavailable }

/// O que a tela precisa saber sobre atualização.
class MobileUpdateStatus {
  const MobileUpdateStatus({
    required this.phase,
    this.installed = '',
    this.release,
    this.apk,
    this.reason = '',
  });

  final UpdatePhase phase;
  final String installed;
  final MobileRelease? release;

  /// O APK escolhido para este aparelho.
  final MobileApk? apk;

  /// Por que não deu para checar. Nunca vira erro de tela: ficar sem saber se há
  /// versão nova não pode impedir o garçom de atender.
  final String reason;

  bool get hasUpdate => phase == UpdatePhase.available && apk != null;
}

/// Checa, baixa e entrega a versão nova do app do garçom.
///
/// NADA AQUI BLOQUEIA O ATENDIMENTO. A checagem falha em silêncio (rede da loja
/// cai, GitHub fora do ar) e o download só começa quando alguém toca no botão —
/// baixar 25 MB sozinho no meio do almoço, no 4G do garçom, é decisão que não
/// cabe ao app tomar.
class MobileUpdateService {
  MobileUpdateService({
    http.Client? client,
    MobileUpdateInstaller? installer,
    this.manifestUrl = urlDoManifestoMovel,
  }) : _client = client ?? http.Client(),
       _installer = installer ?? const MobileUpdateInstaller();

  final http.Client _client;
  final MobileUpdateInstaller _installer;
  final String manifestUrl;

  MobileUpdateInstaller get installer => _installer;

  /// A versão instalada, como o aparelho a conhece.
  Future<String> installedVersion() async {
    try {
      return (await PackageInfo.fromPlatform()).version;
    } catch (_) {
      return '';
    }
  }

  Future<MobileUpdateStatus> check() async {
    final instalada = await installedVersion();
    try {
      final resposta = await _client
          .get(Uri.parse(manifestUrl))
          .timeout(const Duration(seconds: 12));
      if (resposta.statusCode != 200) {
        return MobileUpdateStatus(
          phase: UpdatePhase.unavailable,
          installed: instalada,
          reason: 'O servidor de atualização respondeu ${resposta.statusCode}.',
        );
      }
      final release = MobileRelease.fromJson(
        Map<String, dynamic>.from(jsonDecode(resposta.body) as Map),
      );
      if (instalada.isEmpty || !ehMaisNova(release.version, instalada)) {
        return MobileUpdateStatus(
          phase: UpdatePhase.upToDate,
          installed: instalada,
          release: release,
        );
      }
      return MobileUpdateStatus(
        phase: UpdatePhase.available,
        installed: instalada,
        release: release,
        apk: release.apkPara(await _installer.abi()),
      );
    } on FormatException catch (falha) {
      return MobileUpdateStatus(
        phase: UpdatePhase.unavailable,
        installed: instalada,
        reason: 'Manifesto de atualização inválido: ${falha.message}',
      );
    } catch (_) {
      return MobileUpdateStatus(
        phase: UpdatePhase.unavailable,
        installed: instalada,
        reason: 'Não foi possível consultar as atualizações agora.',
      );
    }
  }

  /// Baixa o APK verificando tamanho e SHA-256 ANTES de entregá-lo.
  ///
  /// A verificação não é zelo: a rede da loja cai no meio do download com
  /// frequência, e um APK truncado que chega ao instalador falha na cara do
  /// garçom sem dizer por quê. Arquivo que não confere é apagado — deixá-lo em
  /// disco faria a próxima tentativa achar que já baixou.
  Future<File> download(MobileApk apk, {void Function(double)? onProgress}) async {
    final pasta = await getTemporaryDirectory();
    final destino = File('${pasta.path}/${apk.name}');
    final parcial = File('${destino.path}.parcial');
    if (await parcial.exists()) await parcial.delete();

    final requisicao = http.Request('GET', apk.url);
    final resposta = await _client.send(requisicao);
    if (resposta.statusCode != 200) {
      throw HttpException('O download respondeu ${resposta.statusCode}.', uri: apk.url);
    }
    final saida = parcial.openWrite();
    var baixado = 0;
    try {
      await for (final pedaco in resposta.stream) {
        saida.add(pedaco);
        baixado += pedaco.length;
        onProgress?.call(apk.size == 0 ? 0 : baixado / apk.size);
      }
    } finally {
      await saida.close();
    }

    final bytes = await parcial.readAsBytes();
    if (bytes.length != apk.size) {
      await parcial.delete();
      throw const FileSystemException(
        'O download veio incompleto. Tente de novo com a rede estável.',
      );
    }
    if (sha256.convert(bytes).toString() != apk.sha256) {
      await parcial.delete();
      throw const FileSystemException(
        'O arquivo baixado não confere com o publicado. O download foi descartado.',
      );
    }
    if (await destino.exists()) await destino.delete();
    await parcial.rename(destino.path);
    return destino;
  }

  void dispose() => _client.close();
}
