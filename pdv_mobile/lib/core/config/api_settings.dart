import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiSettings extends ChangeNotifier {
  ApiSettings._(this._storage, this._baseUrl, [this._askTable = true]);

  static const defaultBaseUrl = 'https://api.starchef.com.br/api/v1';
  static const _storageKey = 'starchef_mobile_api_url';
  static const _askTableKey = 'starchef_mobile_ask_table';

  final FlutterSecureStorage _storage;
  String _baseUrl;

  String get baseUrl => _baseUrl;

  /// Perguntar a mesa ao abrir a comanda (e sugerir ao entrar nela).
  ///
  /// POR APARELHO: a casa que trabalha no balcão desliga, e a pergunta deixa
  /// de ser um toque a mais em todo atendimento. O "Vincular mesa" manual da
  /// tela da comanda continua lá.
  bool get askTable => _askTable;
  bool _askTable;
  bool get isDefault => _baseUrl == defaultBaseUrl;

  static Future<ApiSettings> load() async {
    const storage = FlutterSecureStorage();
    String saved;
    var askTable = true;
    try {
      saved = await storage.read(key: _storageKey) ?? defaultBaseUrl;
      askTable = await storage.read(key: _askTableKey) != 'false';
    } catch (_) {
      saved = defaultBaseUrl;
    }
    return ApiSettings._(storage, normalize(saved), askTable);
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

  Future<void> setAskTable(bool value) async {
    if (value == _askTable) return;
    _askTable = value;
    notifyListeners();
    try {
      await _storage.write(key: _askTableKey, value: '$value');
    } catch (_) {
      // Sem o cofre a escolha vale até fechar o app — melhor que não valer.
    }
  }

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
