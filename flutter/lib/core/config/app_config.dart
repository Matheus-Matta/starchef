import 'dart:io';

class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    this.envFilePath,
    this.usedFallbackApiUrl = false,
    this.sentryDsn,
  });

  static const _fallbackApiUrl = 'http://localhost:8000/api/v1';

  final String apiBaseUrl;
  final String? envFilePath;

  /// True quando nenhuma URL de API foi configurada (nem --dart-define, nem
  /// .env) e o app caiu no fallback de desenvolvimento. Um terminal real
  /// nessa condição "funciona" apontando para lugar nenhum — quem chama
  /// [load] deve tornar isso visível em vez de deixar passar em silêncio.
  final bool usedFallbackApiUrl;

  /// DSN do Sentry (opcional). Sem ela, `main.dart` não inicializa o Sentry —
  /// mesmo critério de "zero overhead sem configuração" usado no backend e
  /// no frontend web.
  final String? sentryDsn;

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
    const definedDsn = String.fromEnvironment('PDV_SENTRY_DSN');

    if (definedUrl.isNotEmpty) {
      // --dart-define resolve a API diretamente; ainda assim tenta achar um
      // .env só para pegar PDV_SENTRY_DSN, se a DSN não veio por --dart-define.
      final dsn = definedDsn.isNotEmpty
          ? definedDsn
          : await _sentryDsnFromEnvFile();
      return AppConfig(apiBaseUrl: definedUrl, sentryDsn: _orNull(dsn));
    }

    final envFile = await EnvFileLoader.find();
    if (envFile == null) {
      return AppConfig(
        apiBaseUrl: _fallbackApiUrl,
        usedFallbackApiUrl: true,
        sentryDsn: _orNull(definedDsn),
      );
    }

    final values = await EnvFileLoader.read(
      envFile,
      allowedKeys: const {
        'VITE_API_BASE_URL',
        'VITE_BACKEND_TARGET',
        'API_BASE_URL',
        'PDV_SENTRY_DSN',
      },
    );
    final explicitApiUrl = values['API_BASE_URL'];
    final viteApiUrl = values['VITE_API_BASE_URL'];
    final backendTarget = values['VITE_BACKEND_TARGET'];
    final apiUrl = _absoluteHttpUrl(explicitApiUrl)
        ? explicitApiUrl
        : _absoluteHttpUrl(viteApiUrl)
        ? viteApiUrl
        : _absoluteHttpUrl(backendTarget)
        ? '${_normalizeUrl(backendTarget!)}/api/v1'
        : _fallbackApiUrl;
    return AppConfig(
      apiBaseUrl: _normalizeUrl(apiUrl!),
      envFilePath: envFile.path,
      usedFallbackApiUrl: apiUrl == _fallbackApiUrl,
      sentryDsn: _orNull(definedDsn.isNotEmpty ? definedDsn : values['PDV_SENTRY_DSN']),
    );
  }

  static Future<String?> _sentryDsnFromEnvFile() async {
    final envFile = await EnvFileLoader.find();
    if (envFile == null) return null;
    final values = await EnvFileLoader.read(
      envFile,
      allowedKeys: const {'PDV_SENTRY_DSN'},
    );
    return values['PDV_SENTRY_DSN'];
  }

  static String? _orNull(String? value) =>
      (value == null || value.trim().isEmpty) ? null : value.trim();

  static bool _absoluteHttpUrl(String? value) {
    if (value == null || value.trim().isEmpty) return false;
    final uri = Uri.tryParse(value.trim());
    return uri != null &&
        (uri.scheme == 'http' || uri.scheme == 'https') &&
        uri.host.isNotEmpty;
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
