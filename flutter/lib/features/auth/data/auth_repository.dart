import '../../../core/network/api_client.dart';
import '../../../core/storage/session_store.dart';
import '../../cash/data/cash_auth_repository.dart';
import '../domain/auth_session.dart';

class AuthRepository {
  const AuthRepository({
    required this.apiClient,
    required this.sessionStore,
    this.cashAuth,
  });

  final ApiClient apiClient;
  final SessionStore sessionStore;
  // Sincroniza/guarda o hash da senha de ações do caixa para uso offline.
  final CashAuthRepository? cashAuth;

  Future<AuthSession> login({
    required String username,
    required String password,
    required bool remember,
  }) async {
    final json = await apiClient.post(
      '/auth/login/',
      // App nativo usa token (Bearer/`?token=`), não cookies httpOnly do navegador.
      // `no_cookie` evita o backend gravar Set-Cookie que o app ignora.
      body: {
        'username': username.trim(),
        'password': password,
        'no_cookie': true,
      },
    );
    final session = AuthSession.fromJson(json);
    if (remember) {
      // A sessão autenticada continua válida em memória mesmo se o cofre do
      // Windows estiver temporariamente indisponível.
      try {
        await sessionStore.save(session).timeout(const Duration(seconds: 5));
      } catch (_) {
        // Persistência é uma conveniência e não deve bloquear o acesso ao PDV.
      }
    }
    // Baixa e guarda o hash da senha do caixa (para autorização offline).
    await cashAuth?.trySync(session);
    return session;
  }

  Future<AuthSession?> restoreSession() async {
    final stored = await sessionStore.read();
    if (stored == null) return null;
    try {
      final userData = await apiClient.get(
        '/auth/me/',
        accessToken: stored.accessToken,
      );
      final refreshed = AuthSession(
        accessToken: stored.accessToken,
        refreshToken: stored.refreshToken,
        user: AuthUser.fromJson(userData),
      );
      await sessionStore.save(refreshed);
      // Online: atualiza o hash da senha do caixa guardado no dispositivo.
      await cashAuth?.trySync(refreshed);
      return refreshed;
    } catch (_) {
      return stored;
    }
  }

  Future<void> logout() async {
    await apiClient.clearSession();
    await sessionStore.clear();
    await cashAuth?.clear();
  }
}
