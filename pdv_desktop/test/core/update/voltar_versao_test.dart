import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_auto_updater.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_troca_de_versao.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_update_installer.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_update_service.dart';
import 'package:starchef_pdv_desktop/core/update/versoes_do_pdv.dart';

/// Voltar o PDV para uma versão anterior, e ele FICAR nela.
///
/// O atualizador só sabia ir para a mais nova: um release com defeito parava
/// a loja até a correção. E voltar à mão não adiantava — a próxima abertura
/// subia de novo para a versão com defeito.
final _zip = PdvReleaseArtifact(
  kind: 'portable',
  format: 'zip',
  name: 'StarChef-PDV-Windows-v3.0.115.zip',
  url: Uri.parse('https://github.com/o/r/releases/download/v3.0.115/x.zip'),
  sha256: 'a',
  size: 1,
  recommended: false,
);

class _Servico extends PdvUpdateService {
  _Servico(this.resultado) : super(platform: 'windows');

  final PdvUpdateStatus resultado;
  final baixados = <String>[];

  @override
  Future<PdvUpdateStatus> check({
    void Function(PdvInstalledVersion installed)? onInstalled,
  }) async => resultado;

  @override
  Future<PdvReleaseManifest> manifestDe(Uri url) async => PdvReleaseManifest(
    version: '3.0.115',
    tag: 'v3.0.115',
    releaseUrl: Uri.parse('https://github.com/o/r/releases/tag/v3.0.115'),
    platforms: {
      'windows': [_zip],
    },
  );

  @override
  Future<PdvDownloadedArtifact> downloadAndVerify(
    PdvReleaseArtifact artifact,
    Directory destination, {
    void Function(int received, int total)? onProgress,
  }) async {
    baixados.add(artifact.name);
    return PdvDownloadedArtifact(artifact: artifact, file: File('x.zip'));
  }

  @override
  void dispose() {}
}

class _Instalador extends PdvUpdateInstaller {
  _Instalador() : super(executable: File('starchef_pdv.exe'));

  final lancados = <String>[];

  @override
  Future<PdvPreparedUpdate> prepare(
    PdvDownloadedArtifact downloaded,
    String version,
  ) async => PdvPreparedUpdate(
    version: version,
    installDirectory: Directory('i'),
    stagingDirectory: Directory('s'),
    backupDirectory: Directory('b'),
    executableName: 'starchef_pdv.exe',
    helperScript: File('h'),
  );

  @override
  Future<void> launch(PdvPreparedUpdate update) async =>
      lancados.add(update.version);
}

final _novaDisponivel = PdvUpdateStatus(
  phase: PdvUpdatePhase.updateAvailable,
  installed: const PdvInstalledVersion(version: '3.0.115'),
  latestVersion: '3.0.122',
  artifact: _zip,
);

void main() {
  String? fixada;
  late VersaoFixada guardada;

  setUp(() {
    fixada = null;
    guardada = VersaoFixada(
      ler: () => fixada,
      gravar: (versao) async => fixada = versao,
    );
  });

  test('a lista traz só a mesma linha, sem a instalada, da mais nova', () {
    Map<String, dynamic> release(String tag, {bool manifesto = true}) => {
      'tag_name': tag,
      'assets': [
        if (manifesto)
          {
            'name': 'latest-desktop.json',
            'browser_download_url':
                'https://github.com/o/r/releases/download/$tag/latest-desktop.json',
          },
      ],
    };

    final versoes = versoesDaLista(
      [
        release('v3.0.115'),
        release('v3.0.122'),
        release('v1.8.9'), // a linha offline: outro programa
        release('v3.0.120'), // a instalada
        release('v3.0.118', manifesto: false), // build do desktop falhou
        {...release('v3.0.121'), 'draft': true},
      ],
      asset: 'latest-desktop.json',
      instalada: '3.0.120',
    );

    expect(versoes.map((v) => v.version), ['3.0.122', '3.0.115']);
  });

  test('versão fixada: a abertura avisa, mas não troca', () async {
    fixada = '3.0.115';
    final servico = _Servico(_novaDisponivel);
    final updater = PdvAutoUpdater(
      service: servico,
      installer: _Instalador(),
      enabled: true,
      versaoFixada: guardada,
    );

    await updater.start(closePdv: () async {});

    expect(servico.baixados, isEmpty);
    expect(updater.status!.phase, PdvUpdatePhase.updateAvailable);
    expect(updater.detail, contains('3.0.115'));
    updater.dispose();
  });

  test('"Buscar atualizações" solta a versão fixada e atualiza', () async {
    fixada = '3.0.115';
    final instalador = _Instalador();
    final updater = PdvAutoUpdater(
      service: _Servico(_novaDisponivel),
      installer: instalador,
      enabled: true,
      versaoFixada: guardada,
    );

    await updater.checkAndInstall(closePdv: () async {});

    expect(fixada, isNull);
    expect(instalador.lancados, ['3.0.122']);
    updater.dispose();
  });

  test('instalar uma versão anterior troca o PDV e a fixa', () async {
    final instalador = _Instalador();
    var fechou = false;
    final updater = PdvAutoUpdater(
      service: _Servico(_novaDisponivel),
      installer: instalador,
      enabled: true,
      versaoFixada: guardada,
    );

    await updater.instalarVersao(
      PdvVersaoDisponivel(
        version: '3.0.115',
        tag: 'v3.0.115',
        manifestUrl: Uri.parse(
          'https://github.com/o/r/releases/download/v3.0.115/latest-desktop.json',
        ),
      ),
      closePdv: () async => fechou = true,
    );

    expect(instalador.lancados, ['3.0.115']);
    expect(fixada, '3.0.115');
    expect(fechou, isTrue);
    updater.dispose();
  });
}
