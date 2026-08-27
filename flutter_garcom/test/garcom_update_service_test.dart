import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/core/update/garcom_update_service.dart';

void main() {
  group('compareGarcomVersions', () {
    test('positivo quando a esquerda é mais nova', () {
      expect(compareGarcomVersions('1.7.0', '1.6.2'), greaterThan(0));
    });

    test('negativo quando a esquerda é mais antiga', () {
      expect(compareGarcomVersions('1.6.1', '1.6.2'), lessThan(0));
    });

    test('zero para a mesma versão', () {
      expect(compareGarcomVersions('1.6.2', '1.6.2'), 0);
    });

    test('ignora o prefixo v e o build number', () {
      expect(compareGarcomVersions('v1.6.2', '1.6.2+9'), 0);
    });
  });

  group('GarcomUpdatePackage.fromJson', () {
    Map<String, dynamic> manifest({Object? garcom}) => {
      'schema_version': 1,
      'garcom': ?garcom,
    };

    test('lê versão, url, sha256 e tamanho do manifesto', () {
      final package = GarcomUpdatePackage.fromJson(
        manifest(
          garcom: {
            'version': '1.7.0',
            'package': {
              'url':
                  'https://github.com/Matheus-Matta/starchef/releases/download/v1.0.38/StarChef-Garcom-v1.7.0.apk',
              'sha256': 'a' * 64,
              'size': 71831708,
            },
          },
        ),
      );
      expect(package.version, '1.7.0');
      expect(package.sha256, 'a' * 64);
      expect(package.size, 71831708);
    });

    test('rejeita manifesto sem a chave garcom', () {
      expect(
        () => GarcomUpdatePackage.fromJson(manifest()),
        throwsFormatException,
      );
    });

    test('rejeita SHA-256 com formato inválido', () {
      expect(
        () => GarcomUpdatePackage.fromJson(
          manifest(
            garcom: {
              'version': '1.7.0',
              'package': {
                'url': 'https://example.com/app.apk',
                'sha256': 'não é um hash',
                'size': 100,
              },
            },
          ),
        ),
        throwsFormatException,
      );
    });

    test('rejeita URL que não seja https', () {
      expect(
        () => GarcomUpdatePackage.fromJson(
          manifest(
            garcom: {
              'version': '1.7.0',
              'package': {
                'url': 'http://example.com/app.apk',
                'sha256': 'a' * 64,
                'size': 100,
              },
            },
          ),
        ),
        throwsFormatException,
      );
    });
  });
}
