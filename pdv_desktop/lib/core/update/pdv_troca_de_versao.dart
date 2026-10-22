import 'dart:io';

import '../logging/app_logger.dart';
import '../storage/app_paths.dart';
import 'pdv_update_installer.dart';
import 'pdv_update_service.dart';

/// Baixar, conferir, preparar e passar para o auxiliar que troca o PDV.
///
/// É o MESMO caminho para ir à versão mais nova e para voltar a uma anterior:
/// tamanho e SHA-256 conferidos, bundle numa pasta nova, troca feita com o PDV
/// fechado e volta automática se a versão escolhida não abrir. Dois caminhos
/// seriam duas chances de um deles pular a conferência.
Future<void> trocarDeVersao({
  required PdvUpdateService service,
  required PdvUpdateInstaller installer,
  required PdvReleaseArtifact artifact,
  required String version,
  required String? from,
  required Future<void> Function() closePdv,
  required void Function(String fase) onFase,
  required void Function(int received, int total) onProgress,
}) async {
  onFase('downloading');
  final downloads = Directory(
    '${AppPaths.dataDirectory().path}${Platform.pathSeparator}updates'
    '${Platform.pathSeparator}$version',
  );
  final downloaded = await service.downloadAndVerify(
    artifact,
    downloads,
    onProgress: onProgress,
  );
  onFase('preparing');
  final prepared = await installer.prepare(downloaded, version);
  await installer.launch(prepared);
  onFase('restarting');
  AppLogger.instance.info(
    'pdv_update_handoff',
    data: {'from': from, 'to': version, 'artifact': artifact.name},
  );
  await closePdv();
}

/// A versão que o operador escolheu manter neste terminal.
///
/// Com ela gravada, a abertura do PDV NÃO atualiza sozinha: voltar para a
/// 3.0.115 e ver o PDV subir de novo para a 3.0.122 no próximo início
/// desfaria a escolha. Ela sai quando alguém pede "Buscar atualizações" ou
/// "Voltar a atualizar sozinho".
class VersaoFixada {
  const VersaoFixada({required this.ler, required this.gravar});

  /// Para quem não grava nada (testes, a janela da balança).
  VersaoFixada.emMemoria() : this(ler: () => null, gravar: _naoGrava);

  final String? Function() ler;
  final Future<void> Function(String? versao) gravar;

  static Future<void> _naoGrava(String? _) async {}
}

/// A falha, em uma frase para o operador: o PDV atual sempre fica.
String mensagemDaFalha(Object error) {
  if (error is FileSystemException && error.message.trim().isNotEmpty) {
    return '${error.message} O PDV atual foi mantido.';
  }
  if (error is FormatException && error.message.trim().isNotEmpty) {
    return '${error.message}. O PDV atual foi mantido.';
  }
  return 'A atualização falhou. O PDV atual foi mantido.';
}
