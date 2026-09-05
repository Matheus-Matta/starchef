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

  group('pickPackageForDevice', () {
    Map<String, Object?> garcom({List<Object?>? packages}) => {
      'version': '1.8.3',
      'package': {'name': 'universal.apk', 'url': 'https://x/u.apk'},
      'packages': ?packages,
    };

    final porAbi = [
      {'abi': 'armeabi-v7a', 'name': 'v7a.apk', 'url': 'https://x/v7a.apk'},
      {'abi': 'arm64-v8a', 'name': 'v8a.apk', 'url': 'https://x/v8a.apk'},
      {'abi': 'x86_64', 'name': 'x64.apk', 'url': 'https://x/x64.apk'},
    ];

    test('escolhe o APK da arquitetura do aparelho', () {
      final escolhido = pickPackageForDevice(
        garcom(packages: porAbi),
        abi: 'arm64-v8a',
      );
      expect(escolhido?['name'], 'v8a.apk');
    });

    test('sem lista por arquitetura, cai no universal', () {
      expect(
        pickPackageForDevice(garcom(), abi: 'arm64-v8a')?['name'],
        'universal.apk',
      );
    });

    test('arquitetura desconhecida cai no universal', () {
      final escolhido = pickPackageForDevice(
        garcom(packages: porAbi),
        abi: 'riscv64',
      );
      expect(escolhido?['name'], 'universal.apk');
    });

    // É o que mantém um release novo instalável a partir de um manifesto
    // herdado de antes desta mudança, quando `packages` não existia.
    test('manifesto sem nenhum pacote devolve nulo', () {
      expect(pickPackageForDevice(const {'version': '1.8.3'}), isNull);
    });
  });
}
