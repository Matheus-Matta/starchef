import 'dart:io';

import 'package:flutter/foundation.dart';

/// Resolve o diretório de dados persistentes do terminal.
///
/// A fila offline precisa sobreviver a reinicializações do computador, então o
/// destino nunca pode ser um diretório temporário quando existir um lugar
/// estável. No Windows usamos `%LOCALAPPDATA%`; no Linux/macOS seguimos o
/// XDG (`$XDG_DATA_HOME`, senão `~/.local/share`). O diretório temporário fica
/// como último recurso para ambientes sem HOME (contêineres, testes).
abstract final class AppPaths {
  static const _folderName = 'StarChef';

  static Directory? _override;

  /// Redireciona o armazenamento — usado pelos testes para não escrever no
  /// diretório real da instalação. Passe `null` para restaurar o padrão.
  @visibleForTesting
  static void overrideDataDirectory(Directory? directory) =>
      _override = directory;

  /// Diretório onde ficam bancos, vínculos de periféricos e preferências.
  static Directory dataDirectory() =>
      _override ??
      Directory('${_baseDirectory()}${Platform.pathSeparator}$_folderName');

  /// Caminho de um arquivo dentro do diretório de dados.
  static File dataFile(String fileName) =>
      File('${dataDirectory().path}${Platform.pathSeparator}$fileName');

  static String _baseDirectory() {
    if (Platform.isWindows) {
      final localAppData = Platform.environment['LOCALAPPDATA']?.trim();
      if (localAppData != null && localAppData.isNotEmpty) return localAppData;
      final appData = Platform.environment['APPDATA']?.trim();
      if (appData != null && appData.isNotEmpty) return appData;
      return Directory.systemTemp.path;
    }

    // `LOCALAPPDATA` continua sendo respeitado fora do Windows para permitir
    // que testes e empacotamentos apontem o armazenamento para outro lugar.
    final override = Platform.environment['LOCALAPPDATA']?.trim();
    if (override != null && override.isNotEmpty) return override;

    final xdgDataHome = Platform.environment['XDG_DATA_HOME']?.trim();
    if (xdgDataHome != null && xdgDataHome.isNotEmpty) return xdgDataHome;

    final home = Platform.environment['HOME']?.trim();
    if (home != null && home.isNotEmpty) {
      return '$home${Platform.pathSeparator}.local'
          '${Platform.pathSeparator}share';
    }
    return Directory.systemTemp.path;
  }
}
