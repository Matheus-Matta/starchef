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

    final xdgDataHome = Platform.environment['XDG_DATA_HOME']?.trim();
    if (xdgDataHome != null && xdgDataHome.isNotEmpty) return xdgDataHome;

    final home = _linuxHomeDirectory();
    if (home != null && home.isNotEmpty) {
      return '$home${Platform.pathSeparator}.local'
          '${Platform.pathSeparator}share';
    }

    // Último recurso: nunca deveria ser alcançado num desktop de verdade, e
    // `/tmp` é justamente o pior lugar para guardar pareamento, fila offline
    // e preferências — algumas distros o limpam a cada boot. Se chegou até
    // aqui, o processo foi iniciado sem `HOME` nem usuário identificável no
    // ambiente (ex.: um serviço systemd mal configurado); é melhor a próxima
    // abertura reconfigurar tudo do que perder dados em silêncio achando que
    // persistiu.
    return Directory.systemTemp.path;
  }

  /// `HOME` é o caminho normal, mas nem todo processo o herda — um serviço
  /// systemd ou um autostart mal configurado pode não repassar o ambiente da
  /// sessão gráfica. Sem isso, o PDV caía direto no diretório temporário (ver
  /// [_baseDirectory]) e perdia o pareamento do Caixa Principal a cada
  /// reinício, mesmo sem o computador ter sido desligado.
  static String? _linuxHomeDirectory() {
    final home = Platform.environment['HOME']?.trim();
    if (home != null && home.isNotEmpty) return home;

    final user =
        Platform.environment['USER']?.trim() ??
        Platform.environment['LOGNAME']?.trim();
    if (user == null || user.isEmpty) return null;
    final guess = Platform.isMacOS ? '/Users/$user' : '/home/$user';
    return Directory(guess).existsSync() ? guess : null;
  }
}
