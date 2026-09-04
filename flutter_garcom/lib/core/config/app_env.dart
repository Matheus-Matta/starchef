import 'package:flutter_dotenv/flutter_dotenv.dart';

/// Configuração de build do app: só o endereço do backend.
///
/// O Caixa Principal (IP, porta e senha de pareamento) NÃO mora aqui de
/// propósito — muda de loja para loja e a senha não pode ser distribuída
/// dentro do pacote. Ela é digitada na tela de login e guardada no cofre do
/// aparelho.
abstract final class AppEnv {
  static const _key = 'BACKEND_URL';

  /// Usado quando o `.env` não traz nada utilizável (build de loja).
  static const fallbackBackendUrl = 'https://api.starchef.com.br/api/v1';

  static Future<void> load() async {
    try {
      await dotenv.load(fileName: '.env');
    } catch (_) {
      // Sem .env o app ainda sobe apontando para a produção: um erro de
      // empacotamento não pode deixar o garçom sem tela de login.
    }
  }

  static String get backendUrl {
    final raw = dotenv.maybeGet(_key)?.trim() ?? '';
    return normalizeBackendUrl(raw.isEmpty ? fallbackBackendUrl : raw);
  }

  /// Aceita `http://192.168.0.10:8001` ou a URL completa com `/api/v1`.
  /// Sem caminho, completa com o namespace usado por todos os endpoints.
  static String normalizeBackendUrl(String value) {
    final trimmed = value.trim().replaceFirst(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(trimmed);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      return fallbackBackendUrl;
    }
    if (uri.path.isEmpty || uri.path == '/') return '$trimmed/api/v1';
    return trimmed;
  }
}
