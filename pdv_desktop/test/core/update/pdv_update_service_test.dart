import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_update_service.dart';

void main() {
  group('comparePdvVersions', () {
    test('compara versões estáveis e ignora build number', () {
      expect(comparePdvVersions('1.2.0', '1.1.9'), greaterThan(0));
      expect(comparePdvVersions('v2.0.0', '2.0.0+31'), 0);
      expect(comparePdvVersions('1.0.0', '1.0.0-beta.2'), greaterThan(0));
    });

    test('rejeita versão fora do padrão da tag', () {
      expect(() => comparePdvVersions('1.2', '1.2.0'), throwsFormatException);
    });
  });

  group('PdvUpdateService', () {
    test('indica atualização e escolhe ZIP transacional no Windows', () async {
      final service = PdvUpdateService(
        manifestUri: Uri.parse('https://updates.example/latest.json'),
        platform: 'windows',
        installedVersionLoader: () async =>
            const PdvInstalledVersion(version: '1.0.32', buildNumber: '30'),
        client: MockClient(
          (_) async => http.Response(
            jsonEncode(_manifest(version: '1.0.33')),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          ),
        ),
      );

      final status = await service.check();

      expect(status.phase, PdvUpdatePhase.updateAvailable);
      expect(status.installed?.display, '1.0.32+30');
      expect(status.latestVersion, '1.0.33');
      expect(status.artifact?.kind, 'portable');
      expect(status.artifact?.format, 'zip');
      service.dispose();
    });

    test('considera versão igual atualizada no Linux', () async {
      final service = PdvUpdateService(
        manifestUri: Uri.parse('https://updates.example/latest.json'),
        platform: 'linux',
        installedVersionLoader: () async =>
            const PdvInstalledVersion(version: '1.0.33'),
        client: MockClient(
          (_) async => http.Response(jsonEncode(_manifest()), 200),
        ),
      );

      final status = await service.check();

      expect(status.phase, PdvUpdatePhase.upToDate);
      expect(status.artifact?.kind, 'portable');
      expect(status.artifact?.format, 'zip');
      service.dispose();
    });

    test('falha de rede não impede identificar a versão instalada', () async {
      final service = PdvUpdateService(
        manifestUri: Uri.parse('https://updates.example/latest.json'),
        installedVersionLoader: () async =>
            const PdvInstalledVersion(version: '1.0.33'),
        client: MockClient((_) async => http.Response('indisponível', 503)),
      );

      final status = await service.check();

      expect(status.phase, PdvUpdatePhase.unavailable);
      expect(status.installed?.version, '1.0.33');
      expect(status.detail, contains('HTTP 503'));
      service.dispose();
    });

    // ── o 404 do release recém-criado ──────────────────────────────────────
    //
    // Foi este caso que parou a atualização automática na 3.0. O Release da
    // tag nova é criado pelo workflow do atendimento móvel, que termina em
    // minutos; o build do desktop leva mais de dez. Nesse intervalo
    // `releases/latest/download/latest-desktop.json` responde 404 — e um build
    // de desktop que falha deixa a tag assim para sempre.
    test(
      'cai para a API de releases quando o latest ainda não tem o manifesto',
      () async {
        final chamadas = <String>[];
        final service = PdvUpdateService(
          manifestUri: Uri.parse(
            'https://github.com/example/starchef/releases/latest/download/latest-desktop.json',
          ),
          platform: 'windows',
          installedVersionLoader: () async =>
              const PdvInstalledVersion(version: '1.0.32'),
          client: MockClient((request) async {
            chamadas.add(request.url.toString());
            if (request.url.host == 'github.com') {
              return http.Response('Not Found', 404);
            }
            if (request.url.host == 'api.github.com') {
              return http.Response(
                jsonEncode([
                  // O release novo existe, mas só com o pacote do mobile.
                  {
                    'tag_name': 'v1.0.34',
                    'draft': false,
                    'assets': [
                      {
                        'name': 'latest-mobile.json',
                        'browser_download_url':
                            'https://objects.example/latest-mobile.json',
                      },
                    ],
                  },
                  {
                    'tag_name': 'v1.0.33',
                    'draft': false,
                    'assets': [
                      {
                        'name': 'latest-desktop.json',
                        'browser_download_url':
                            'https://objects.example/latest-desktop.json',
                      },
                    ],
                  },
                ]),
                200,
              );
            }
            return http.Response(jsonEncode(_manifest(version: '1.0.33')), 200);
          }),
        );

        final status = await service.check();

        expect(status.phase, PdvUpdatePhase.updateAvailable);
        expect(status.latestVersion, '1.0.33');
        // Consultou a API só depois do 404, e foi buscar o manifesto certo.
        expect(chamadas.length, 3);
        expect(chamadas[1], contains('api.github.com'));
        expect(chamadas[2], contains('latest-desktop.json'));
        service.dispose();
      },
    );

    test('ignora release em rascunho ao procurar o manifesto', () async {
      final service = PdvUpdateService(
        manifestUri: Uri.parse(
          'https://github.com/example/starchef/releases/latest/download/latest-desktop.json',
        ),
        platform: 'windows',
        installedVersionLoader: () async =>
            const PdvInstalledVersion(version: '1.0.32'),
        client: MockClient((request) async {
          if (request.url.host == 'github.com') {
            return http.Response('Not Found', 404);
          }
          if (request.url.host == 'api.github.com') {
            return http.Response(
              jsonEncode([
                {
                  'tag_name': 'v9.9.9',
                  'draft': true,
                  'assets': [
                    {
                      'name': 'latest-desktop.json',
                      'browser_download_url':
                          'https://objects.example/rascunho.json',
                    },
                  ],
                },
                {
                  'tag_name': 'v1.0.33',
                  'draft': false,
                  'assets': [
                    {
                      'name': 'latest-desktop.json',
                      'browser_download_url':
                          'https://objects.example/latest-desktop.json',
                    },
                  ],
                },
              ]),
              200,
            );
          }
          expect(request.url.path, isNot(contains('rascunho')));
          return http.Response(jsonEncode(_manifest(version: '1.0.33')), 200);
        }),
      );

      final status = await service.check();

      expect(status.latestVersion, '1.0.33');
      service.dispose();
    });

    test('manifesto fora do GitHub não consulta API nenhuma', () async {
      final chamadas = <String>[];
      final service = PdvUpdateService(
        manifestUri: Uri.parse('https://updates.example/latest-desktop.json'),
        platform: 'windows',
        installedVersionLoader: () async =>
            const PdvInstalledVersion(version: '1.0.32'),
        client: MockClient((request) async {
          chamadas.add(request.url.host);
          return http.Response('Not Found', 404);
        }),
      );

      final status = await service.check();

      expect(status.phase, PdvUpdatePhase.unavailable);
      expect(status.detail, contains('HTTP 404'));
      expect(chamadas, ['updates.example']);
      service.dispose();
    });

    test('API fora do ar mantém o erro original, sem piorar nada', () async {
      final service = PdvUpdateService(
        manifestUri: Uri.parse(
          'https://github.com/example/starchef/releases/latest/download/latest-desktop.json',
        ),
        platform: 'windows',
        installedVersionLoader: () async =>
            const PdvInstalledVersion(version: '1.0.32'),
        client: MockClient((request) async {
          if (request.url.host == 'api.github.com') {
            return http.Response('rate limit', 403);
          }
          return http.Response('Not Found', 404);
        }),
      );

      final status = await service.check();

      expect(status.phase, PdvUpdatePhase.unavailable);
      expect(status.detail, contains('HTTP 404'));
      expect(status.installed?.version, '1.0.32');
      service.dispose();
    });

    test('nenhum release com manifesto não vira falso "atualizado"', () async {
      final service = PdvUpdateService(
        manifestUri: Uri.parse(
          'https://github.com/example/starchef/releases/latest/download/latest-desktop.json',
        ),
        platform: 'windows',
        installedVersionLoader: () async =>
            const PdvInstalledVersion(version: '1.0.32'),
        client: MockClient((request) async {
          if (request.url.host == 'api.github.com') {
            return http.Response(jsonEncode(const []), 200);
          }
          return http.Response('Not Found', 404);
        }),
      );

      final status = await service.check();

      expect(status.phase, PdvUpdatePhase.unavailable);
      service.dispose();
    });

    test('baixa apenas quando tamanho e SHA-256 conferem', () async {
      final bytes = utf8.encode('bundle-starchef');
      final directory = await Directory.systemTemp.createTemp('pdv-update-');
      final artifact = PdvReleaseArtifact(
        kind: 'portable',
        format: 'zip',
        name: 'pdv.zip',
        url: Uri.parse('https://updates.example/pdv.zip'),
        sha256: sha256.convert(bytes).toString(),
        size: bytes.length,
        recommended: true,
      );
      final service = PdvUpdateService(
        client: MockClient((_) async => http.Response.bytes(bytes, 200)),
      );

      final result = await service.downloadAndVerify(artifact, directory);

      expect(await result.file.readAsBytes(), bytes);
      expect(File('${result.file.path}.part').existsSync(), isFalse);
      service.dispose();
      await directory.delete(recursive: true);
    });

    test('remove download quando o SHA-256 diverge', () async {
      final bytes = utf8.encode('conteúdo adulterado');
      final directory = await Directory.systemTemp.createTemp('pdv-update-');
      final artifact = PdvReleaseArtifact(
        kind: 'portable',
        format: 'zip',
        name: 'pdv.zip',
        url: Uri.parse('https://updates.example/pdv.zip'),
        sha256: '0' * 64,
        size: bytes.length,
        recommended: true,
      );
      final service = PdvUpdateService(
        client: MockClient((_) async => http.Response.bytes(bytes, 200)),
      );

      await expectLater(
        service.downloadAndVerify(artifact, directory),
        throwsFormatException,
      );

      expect(File('${directory.path}/pdv.zip.part').existsSync(), isFalse);
      service.dispose();
      await directory.delete(recursive: true);
    });
  });
}

Map<String, dynamic> _manifest({String version = '1.0.33'}) => {
  'schema_version': 1,
  'version': version,
  'tag': 'v$version',
  'release_url': 'https://github.com/example/starchef/releases/tag/v$version',
  'platforms': {
    'windows': {
      'packages': [
        {
          'kind': 'installer',
          'format': 'exe',
          'name': 'StarChef-PDV-Setup-$version.exe',
          'url':
              'https://github.com/example/starchef/releases/download/v$version/StarChef-PDV-Setup-$version.exe',
          'sha256': 'a' * 64,
          'size': 120,
          'recommended': true,
        },
        {
          'kind': 'portable',
          'format': 'zip',
          'name': 'StarChef-PDV-Windows-v$version.zip',
          'url':
              'https://github.com/example/starchef/releases/download/v$version/StarChef-PDV-Windows-v$version.zip',
          'sha256': 'b' * 64,
          'size': 100,
          'recommended': false,
        },
      ],
    },
    'linux': {
      'packages': [
        {
          'kind': 'portable',
          'format': 'zip',
          'name': 'StarChef-PDV-Linux-v$version.zip',
          'url':
              'https://github.com/example/starchef/releases/download/v$version/StarChef-PDV-Linux-v$version.zip',
          'sha256': 'c' * 64,
          'size': 100,
          'recommended': true,
        },
      ],
    },
  },
};
