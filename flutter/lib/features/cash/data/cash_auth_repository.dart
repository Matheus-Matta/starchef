import '../../../core/network/api_client.dart';
import '../../../core/security/cash_password.dart';
import '../../auth/domain/auth_session.dart';
import 'cash_auth_store.dart';

/// Sincroniza (online) o hash da senha de ações do caixa do restaurante do
/// usuário e o guarda com segurança para VERIFICAÇÃO OFFLINE quando não houver
/// rede — liberando ações do caixa que exigem autorização.
class CashAuthRepository {
  CashAuthRepository({required this.apiClient, CashAuthStore? store})
    : store = store ?? CashAuthStore();

  final ApiClient apiClient;
  final CashAuthStore store;

  /// Baixa o hash do backend e persiste localmente. Silencioso em falha
  /// (offline/sem permissão): mantém o hash já guardado.
  Future<void> trySync(AuthSession session, {String? restaurantId}) async {
    restaurantId ??= session.user.restaurantId;
    if (restaurantId == null || restaurantId.isEmpty) return;
    try {
      final json = await apiClient.get(
        '/restaurants/$restaurantId/cash-auth/',
        accessToken: session.accessToken,
      );
      final algorithm = '${json['algorithm'] ?? ''}';
      final hash = json['password_hash'] as String?;
      if (algorithm == 'pbkdf2_sha256' && hash != null && hash.isNotEmpty) {
        await store.saveHash(restaurantId, hash);
      } else {
        await store.clear(restaurantId); // restaurante sem senha definida
      }
    } catch (_) {
      // Offline ou sem permissão: preserva o hash local (se existir).
    }
  }

  /// Verifica a senha OFFLINE contra o hash guardado.
  /// Retorna false se não houver senha definida/guardada.
  Future<bool> verify(String password, {required String restaurantId}) async {
    final hash = await store.readHash(restaurantId);
    if (hash == null || hash.isEmpty) return false;
    return CashPassword.verify(password, hash);
  }

  /// Há uma senha de caixa guardada para uso offline?
  Future<bool> hasStoredPassword(String restaurantId) async {
    final hash = await store.readHash(restaurantId);
    return hash != null && hash.isNotEmpty;
  }

  Future<void> clear() => store.clearAll();
}
