import 'dart:io';

class AppConfig {
  const AppConfig({required this.apiBaseUrl, this.envFilePath});

  static const _fallbackApiUrl = 'http://localhost:8000/api/v1';

  final String apiBaseUrl;
  final String? envFilePath;

  /// Base do WebSocket derivada da API (http→ws, https→wss), sem o sufixo
  /// `/api/v1`. Ex.: `http://host:8001/api/v1` → `ws://host:8001`.
  String get webSocketBaseUrl {
    final base = apiBaseUrl.replaceFirst(RegExp(r'/api/v\d+/?$'), '');
    return base.replaceFirst(RegExp(r'^http'), 'ws');
  }

  /// URL do WS de notificações. O app nativo autentica pelo token na query
  /// (`?token=`) — não há cookie nem Origin de navegador.
  String notificationsSocketUrl(String accessToken) =>
      '$webSocketBaseUrl/ws/notifications/?token=${Uri.encodeComponent(accessToken)}';

  static Future<AppConfig> load() async {
    const definedUrl = String.fromEnvironment('API_BASE_URL');
    if (definedUrl.isNotEmpty) {
      return const AppConfig(apiBaseUrl: definedUrl);
    }

    final envFile = await EnvFileLoader.find();
    if (envFile == null) {
      return const AppConfig(apiBaseUrl: _fallbackApiUrl);
    }

    final values = await EnvFileLoader.read(
      envFile,
      allowedKeys: const {'VITE_API_BASE_URL', 'API_BASE_URL'},
    );
    final apiUrl = values['VITE_API_BASE_URL'] ?? values['API_BASE_URL'];
    return AppConfig(
      apiBaseUrl: _normalizeUrl(apiUrl ?? _fallbackApiUrl),
      envFilePath: envFile.path,
    );
  }

  static String _normalizeUrl(String value) =>
      value.trim().replaceFirst(RegExp(r'/$'), '');
}

abstract final class EnvFileLoader {
  static Future<File?> find() async {
    const explicitPath = String.fromEnvironment('STAR_CHEF_ENV_PATH');
    if (explicitPath.isNotEmpty) {
      final file = File(explicitPath);
      return await file.exists() ? file : null;
    }

    final starts = <Directory>[
      Directory.current,
      File(Platform.resolvedExecutable).parent,
    ];
    final visited = <String>{};

    for (final start in starts) {
      var directory = start.absolute;
      for (var depth = 0; depth < 8; depth++) {
        if (visited.add(directory.path)) {
          final candidate = File(
            '${directory.path}${Platform.pathSeparator}.env',
          );
          if (await candidate.exists()) return candidate;
        }
        final parent = directory.parent;
        if (parent.path == directory.path) break;
        directory = parent;
      }
    }
    return null;
  }

  static Future<Map<String, String>> read(
    File file, {
    Set<String>? allowedKeys,
  }) async {
    final values = <String, String>{};
    for (final rawLine in await file.readAsLines()) {
      var line = rawLine.trim();
      if (line.isEmpty || line.startsWith('#')) continue;
      if (line.startsWith('export ')) line = line.substring(7).trimLeft();
      final separator = line.indexOf('=');
      if (separator <= 0) continue;

      final key = line.substring(0, separator).trim();
      if (allowedKeys != null && !allowedKeys.contains(key)) continue;
      var value = line.substring(separator + 1).trim();
      if (value.length >= 2 &&
          ((value.startsWith('"') && value.endsWith('"')) ||
              (value.startsWith("'") && value.endsWith("'")))) {
        value = value.substring(1, value.length - 1);
      }
      values[key] = value;
    }
    return values;
  }
}
