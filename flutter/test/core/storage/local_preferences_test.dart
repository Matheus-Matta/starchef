import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/storage/local_preferences.dart';

void main() {
  late Directory directory;
  late File file;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-prefs');
    file = File('${directory.path}${Platform.pathSeparator}preferences.json');
  });

  tearDown(() async {
    if (await directory.exists()) await directory.delete(recursive: true);
  });

  test('usa os padrões quando o arquivo ainda não existe', () async {
    final preferences = LocalPreferences(file: file);
    await preferences.load();

    expect(preferences.themeMode, ThemeMode.light);
    expect(preferences.commandTimeout, const Duration(seconds: 45));
    expect(preferences.stabilityToleranceKg, 0.002);
    expect(preferences.audibleAlerts, isTrue);
    expect(preferences.autoPrint, isTrue);
  });

  test('o tema gravado volta na próxima abertura', () async {
    final first = LocalPreferences(file: file);
    await first.load();
    await first.setThemeMode(ThemeMode.dark);

    final second = LocalPreferences(file: file);
    await second.load();

    expect(second.themeMode, ThemeMode.dark);
  });

  test('o valor novo já vale antes de terminar a gravação', () async {
    final preferences = LocalPreferences(file: file);
    await preferences.load();

    // A interface troca o tema na hora; o disco é atualizado depois.
    final writing = preferences.setThemeMode(ThemeMode.dark);
    expect(preferences.themeMode, ThemeMode.dark);

    await writing;
    expect(await file.exists(), isTrue);
  });

  test('um JSON corrompido não impede a abertura do PDV', () async {
    await file.parent.create(recursive: true);
    await file.writeAsString('{ isto não é json');

    final preferences = LocalPreferences(file: file);
    await preferences.load();

    expect(preferences.themeMode, ThemeMode.light);
  });

  test('timeout e tolerância ficam dentro dos limites seguros', () async {
    final preferences = LocalPreferences(file: file);
    await preferences.load();

    await preferences.setCommandTimeout(const Duration(seconds: 2));
    expect(preferences.commandTimeout, const Duration(seconds: 10));

    await preferences.setCommandTimeout(const Duration(hours: 5));
    expect(preferences.commandTimeout, const Duration(seconds: 600));

    await preferences.setStabilityToleranceKg(10);
    expect(preferences.stabilityToleranceKg, 0.5);
  });

  test('gravações consecutivas preservam todos os campos', () async {
    final preferences = LocalPreferences(file: file);
    await preferences.load();

    await preferences.setThemeMode(ThemeMode.dark);
    await preferences.setAudibleAlerts(false);
    await preferences.setCommandTimeout(const Duration(seconds: 90));

    final reloaded = LocalPreferences(file: file);
    await reloaded.load();

    expect(reloaded.themeMode, ThemeMode.dark);
    expect(reloaded.audibleAlerts, isFalse);
    expect(reloaded.commandTimeout, const Duration(seconds: 90));
  });

  test(
    'porta serial livre persiste e sobrepõe o caminho deste terminal',
    () async {
      final preferences = LocalPreferences(file: file);
      await preferences.load();
      await preferences.setSerialPort(
        kind: 'printer',
        deviceId: 'printer-1',
        value: '/dev/ttyUSB0',
      );
      await preferences.setSerialPort(
        kind: 'scale',
        deviceId: 'scale-1',
        value: 'COM17',
      );

      final reloaded = LocalPreferences(file: file);
      await reloaded.load();

      expect(
        reloaded.applySerialPort({
          'id': 'printer-1',
          'endpoint': 'COM1',
          'connection_type': 'serial',
        }, kind: 'printer')['endpoint'],
        '/dev/ttyUSB0',
      );
      expect(
        reloaded.applySerialPort({
          'id': 'scale-1',
          'port': 'COM2',
        }, kind: 'scale')['port'],
        'COM17',
      );
    },
  );
}
