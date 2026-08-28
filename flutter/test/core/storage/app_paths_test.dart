import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/storage/app_paths.dart';

void main() {
  tearDown(() => AppPaths.overrideDataDirectory(null));

  test('o diretório padrão termina em StarChef', () {
    expect(AppPaths.dataDirectory().path, endsWith('StarChef'));
  });

  test('a fila offline nunca cai no diretório temporário do sistema', () {
    // Em `/tmp` os dados pendentes não sobreviveriam a uma reinicialização.
    final path = AppPaths.dataDirectory().path;
    final temporary = Directory.systemTemp.path;

    // Em ambientes sem HOME nem LOCALAPPDATA o temporário é o último recurso;
    // em qualquer máquina de operação real isso não deve acontecer.
    final hasStableHome =
        (Platform.environment['LOCALAPPDATA']?.trim().isNotEmpty ?? false) ||
        (Platform.environment['APPDATA']?.trim().isNotEmpty ?? false) ||
        (Platform.environment['XDG_DATA_HOME']?.trim().isNotEmpty ?? false) ||
        (Platform.environment['HOME']?.trim().isNotEmpty ?? false);

    if (hasStableHome) {
      expect(path.startsWith(temporary), isFalse);
    }
  });

  test('dataFile fica dentro do diretório de dados', () {
    final file = AppPaths.dataFile('offline_data.sqlite');

    expect(file.path, startsWith(AppPaths.dataDirectory().path));
    expect(file.path, endsWith('offline_data.sqlite'));
  });

  test('a sobrescrita redireciona todo o armazenamento', () {
    final custom = Directory('${Directory.systemTemp.path}/starchef-custom');
    AppPaths.overrideDataDirectory(custom);

    expect(AppPaths.dataDirectory().path, custom.path);
    expect(AppPaths.dataFile('preferences.json').path, startsWith(custom.path));

    AppPaths.overrideDataDirectory(null);
    expect(AppPaths.dataDirectory().path, endsWith('StarChef'));
  });

  test('valida que o diretório persistente aceita gravação', () async {
    final root = await Directory.systemTemp.createTemp('starchef-paths-test-');
    final custom = Directory('${root.path}/data');
    AppPaths.overrideDataDirectory(custom);

    try {
      await AppPaths.verifyPersistentStorage();

      expect(await custom.exists(), isTrue);
      expect(
        custom.listSync().whereType<File>().map((file) => file.path),
        isEmpty,
      );
    } finally {
      AppPaths.overrideDataDirectory(null);
      await root.delete(recursive: true);
    }
  });
}
