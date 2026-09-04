import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/update/pdv_update_service.dart';

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
