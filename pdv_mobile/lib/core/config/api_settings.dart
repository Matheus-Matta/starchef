import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiSettings extends ChangeNotifier {
  ApiSettings._(this._storage, this._baseUrl);

  static const defaultBaseUrl = 'https://api.starchef.com.br/api/v1';
  static const _storageKey = 'starchef_mobile_api_url';

  final FlutterSecureStorage _storage;
  String _baseUrl;

  String get baseUrl => _baseUrl;
  bool get isDefault => _baseUrl == defaultBaseUrl;

  static Future<ApiSettings> load() async {
    const storage = FlutterSecureStorage();
    String saved;
    try {
      saved = await storage.read(key: _storageKey) ?? defaultBaseUrl;
    } catch (_) {
      saved = defaultBaseUrl;
    }
    return ApiSettings._(storage, normalize(saved));
  }

  Future<void> save(String value) async {
    final normalized = normalize(value);
    if (!isValid(normalized)) {
      throw const FormatException('Informe uma URL HTTP ou HTTPS válida.');
    }
    if (normalized == _baseUrl) return;
    _baseUrl = normalized;
    await _storage.write(key: _storageKey, value: normalized);
    notifyListeners();
  }

  Future<void> reset() => save(defaultBaseUrl);

  static String normalize(String value) {
    var normalized = value.trim().replaceFirst(RegExp(r'/+$'), '');
    if (normalized.isEmpty) return defaultBaseUrl;
    final uri = Uri.tryParse(normalized);
    if (uri != null && (uri.path.isEmpty || uri.path == '/')) {
      normalized = '$normalized/api/v1';
    }
    return normalized;
  }

  static bool isValid(String value) {
    final uri = Uri.tryParse(value);
    return uri != null &&
        (uri.scheme == 'http' || uri.scheme == 'https') &&
        uri.host.isNotEmpty;
  }
}
