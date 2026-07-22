import '../../../core/network/api_client.dart';
import '../../../core/storage/session_store.dart';
import '../domain/auth_session.dart';

class AuthRepository {
  const AuthRepository({required this.apiClient, required this.sessionStore});

  final ApiClient apiClient;
  final SessionStore sessionStore;

  Future<AuthSession> login({
    required String username,
    required String password,
    required bool remember,
  }) async {
    final json = await apiClient.post(
      '/auth/login/',
      body: {'username': username.trim(), 'password': password},
    );
    final session = AuthSession.fromJson(json);
    if (remember) await sessionStore.save(session);
    return session;
  }

  Future<AuthSession?> restoreSession() => sessionStore.read();
  Future<void> logout() => sessionStore.clear();
}
