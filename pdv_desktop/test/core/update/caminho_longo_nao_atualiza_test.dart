import 'dart:io';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/storage/app_paths.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_update_installer.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_update_service.dart';

/// Atualizar para dentro de um caminho longo demais produz um PDV que não abre.
///
/// Aconteceu em campo. A troca antiga renomeava a instalação inteira, e cada
/// atualização acrescentava `.starchef-new-<versão>-<pid>` ao nome da pasta.
/// Depois de algumas, o caminho passou do limite do Windows e o aplicativo
/// parou de ABRIR — com um diálogo que fala em inicialização (`0xC0000106`,
/// `STATUS_NAME_TOO_LONG`) e não diz uma palavra sobre caminho.
///
/// O pior era o beco sem saída: quem caía nesse estado não conseguia nem se
/// atualizar para a correção, porque o PDV não subia para checar atualização.
///
/// A troca de hoje move item a item e não renomeia mais nada. Esta trava é a
/// rede — se o caminho já for longo, a atualização para com um recado que diz
/// o que fazer, em vez de produzir uma instalação morta.
void main() {
  late Directory raiz;
  late File zip;
  late PdvReleaseArtifact artefato;

  const nomeDoExecutavel = 'starchef_pdv_desktop.exe';

  setUp(() async {
    raiz = await Directory.systemTemp.createTemp('pdv-caminho-');
    AppPaths.overrideDataDirectory(
      Directory('${raiz.path}${Platform.pathSeparator}dados'),
    );
    final pacote = Archive()
      ..addFile(ArchiveFile.bytes(nomeDoExecutavel, [1, 2, 3, 4]));
    final bytes = ZipEncoder().encode(pacote);
    zip = File('${raiz.path}${Platform.pathSeparator}pdv.zip');
    await zip.writeAsBytes(bytes);
    artefato = PdvReleaseArtifact(
      kind: 'portable',
      format: 'zip',
      name: 'pdv.zip',
      url: Uri.parse('https://updates.example/pdv.zip'),
      sha256: sha256.convert(bytes).toString(),
      size: bytes.length,
      recommended: true,
    );
  });

  tearDown(() async {
    if (await raiz.exists()) await raiz.delete(recursive: true);
  });

  Future<File> executavelEm(Directory instalacao) async {
    await instalacao.create(recursive: true);
    final exe = File(
      '${instalacao.path}${Platform.pathSeparator}$nomeDoExecutavel',
    );
    await exe.writeAsString('versão anterior');
    return exe;
  }

  test('o teto existe e deixa folga para o pacote e o sufixo', () {
    // instalação + sufixo de transação (~26) + separador + 91 (o arquivo mais
    // fundo do pacote) precisa caber nos 260 do Win32.
    const sufixoDeTransacao = 26;
    const arquivoMaisFundo = 91;
    expect(
      PdvUpdateInstaller.maximoDoCaminhoDeInstalacao +
          sufixoDeTransacao +
          1 +
          arquivoMaisFundo,
      lessThan(260),
    );
  });

  test('a instalação padrão do instalador passa FOLGADA no teto', () {
    // `{localappdata}\\Programs\\StarChef PDV` — o que o Inno Setup usa.
    const padrao = r'C:\Users\operador\AppData\Local\Programs\StarChef PDV';

    expect(
      padrao.length,
      lessThan(PdvUpdateInstaller.maximoDoCaminhoDeInstalacao),
    );
  });

  test('caminho curto atualiza normalmente', () async {
    final instalacao = Directory(
      '${raiz.path}${Platform.pathSeparator}atual',
    );
    final exe = await executavelEm(instalacao);

    final preparado = await PdvUpdateInstaller(executable: exe).prepare(
      PdvDownloadedArtifact(artifact: artefato, file: zip),
      '1.2.3',
    );

    expect(preparado.stagingDirectory.existsSync(), isTrue);
  }, skip: !Platform.isWindows ? false : null);

  test(
    'caminho longo demais é RECUSADO, e o recado diz o que fazer',
    () async {
      // O formato exato que o defeito antigo produzia: um sufixo por
      // atualização, empilhado no nome da pasta.
      final empilhado = List.generate(
        6,
        (i) => '.starchef-new-3.0.${17 + i}-${30000 + i}',
      ).join();
      final instalacao = Directory(
        '${raiz.path}${Platform.pathSeparator}starchef$empilhado',
      );
      final exe = await executavelEm(instalacao);

      await expectLater(
        PdvUpdateInstaller(executable: exe).prepare(
          PdvDownloadedArtifact(artifact: artefato, file: zip),
          '1.2.3',
        ),
        throwsA(
          isA<FileSystemException>().having(
            (e) => e.message,
            'mensagem',
            allOf(contains('caracteres'), contains('pasta mais curta')),
          ),
        ),
      );
    },
    // A trava é do Windows: é lá que 260 caracteres derrubam o carregamento.
    skip: !Platform.isWindows,
  );
}
