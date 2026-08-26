import 'dart:convert';

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
    test('indica atualização e escolhe instalador no Windows', () async {
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
      expect(status.artifact?.kind, 'installer');
      expect(status.artifact?.format, 'exe');
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
          'recommended': true,
        },
        {
          'kind': 'portable',
          'format': 'zip',
          'name': 'StarChef-PDV-Windows-v$version.zip',
          'url':
              'https://github.com/example/starchef/releases/download/v$version/StarChef-PDV-Windows-v$version.zip',
          'sha256': 'b' * 64,
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
          'recommended': true,
        },
      ],
    },
  },
};
