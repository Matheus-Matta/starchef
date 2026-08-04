import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/config/app_config.dart';

void main() {
  test('lê variáveis, comentários, export e valores entre aspas', () async {
    final directory = await Directory.systemTemp.createTemp(
      'starchef_env_test',
    );
    addTearDown(() => directory.delete(recursive: true));
    final file = File('${directory.path}${Platform.pathSeparator}.env');
    await file.writeAsString('''
# configuração compartilhada
export VITE_API_BASE_URL="https://api.starchef.test/api/v1"
IGNORED_LINE
EMPTY=
''');

    final values = await EnvFileLoader.read(file);

    expect(values['VITE_API_BASE_URL'], 'https://api.starchef.test/api/v1');
    expect(values['EMPTY'], isEmpty);
    expect(values.containsKey('IGNORED_LINE'), isFalse);
  });

  test(
    'app nativo ignora URL relativa do Vite e usa o backend absoluto',
    () async {
      final originalDirectory = Directory.current;
      final directory = await Directory.systemTemp.createTemp(
        'starchef_config_',
      );
      addTearDown(() {
        Directory.current = originalDirectory;
        return directory.delete(recursive: true);
      });
      await File(
        '${directory.path}${Platform.pathSeparator}.env',
      ).writeAsString('''
VITE_API_BASE_URL=/api/v1
VITE_BACKEND_TARGET=https://backend.starchef.test
''');
      Directory.current = directory;

      final config = await AppConfig.load();

      expect(config.apiBaseUrl, 'https://backend.starchef.test/api/v1');
      expect(config.usedFallbackApiUrl, isFalse);
    },
  );

  test(
    'sem --dart-define e sem .env, cai no fallback e sinaliza isso',
    () async {
      final originalDirectory = Directory.current;
      final directory = await Directory.systemTemp.createTemp(
        'starchef_config_no_env_',
      );
      addTearDown(() {
        Directory.current = originalDirectory;
        return directory.delete(recursive: true);
      });
      Directory.current = directory;

      final config = await AppConfig.load();

      expect(config.apiBaseUrl, 'http://localhost:8000/api/v1');
      expect(config.usedFallbackApiUrl, isTrue);
    },
  );

  test(
    'override manual (engrenagem do login) tem prioridade e não conta como fallback',
    () async {
      final originalDirectory = Directory.current;
      final directory = await Directory.systemTemp.createTemp(
        'starchef_config_override_',
      );
      addTearDown(() {
        Directory.current = originalDirectory;
        return directory.delete(recursive: true);
      });
      await File(
        '${directory.path}${Platform.pathSeparator}.env',
      ).writeAsString('API_BASE_URL=https://backend-do-env.starchef.test/api/v1\n');
      Directory.current = directory;

      final config = await AppConfig.load(
        manualOverrideUrl: 'https://manual.starchef.test/api/v1',
      );

      expect(config.apiBaseUrl, 'https://manual.starchef.test/api/v1');
      expect(config.usedFallbackApiUrl, isFalse);
    },
  );

  test('override manual inválido é ignorado, cai pro resto da cadeia', () async {
    final originalDirectory = Directory.current;
    final directory = await Directory.systemTemp.createTemp(
      'starchef_config_bad_override_',
    );
    addTearDown(() {
      Directory.current = originalDirectory;
      return directory.delete(recursive: true);
    });
    Directory.current = directory;

    final config = await AppConfig.load(manualOverrideUrl: 'nao-e-uma-url');

    expect(config.apiBaseUrl, 'http://localhost:8000/api/v1');
    expect(config.usedFallbackApiUrl, isTrue);
  });
}
