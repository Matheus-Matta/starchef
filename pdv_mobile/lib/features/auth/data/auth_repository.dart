import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/storage/session_store.dart';
import '../../../core/sync/operation_id.dart';
import '../domain/waiter_session.dart';

class AuthRepository {
  AuthRepository({required this.api, required this.store});

  final ApiClient api;
  final SessionStorage store;

  Future<WaiterSession> login({
    required String username,
    required String password,
  }) async {
    final json = await api.post(
      '/auth/login/',
      body: {
        'username': username.trim(),
        'password': password,
        'no_cookie': true,
        'client': 'waiter_app',
      },
    );
    final user = _userFrom(json);
    if (user.restaurantId.isEmpty) {
      throw const ApiException(
        'Seu usuário não está vinculado a um restaurante.',
      );
    }
    final session = WaiterSession(
      accessToken: '${json['access'] ?? ''}',
      refreshToken: '${json['refresh'] ?? ''}',
      user: user,
    );
    await store.saveSession(session);
    return session;
  }

  Future<String> nodeId() async {
    final current = await store.readNodeId();
    if (current != null && current.length >= 8) return current;
    final generated = OperationId.random();
    await store.saveNodeId(generated);
    return generated;
  }

  Future<void> logout() => store.clearSession();

  static WaiterUser _userFrom(Map<String, dynamic> json) {
    final raw = json['user'];
    final user = raw is Map
        ? Map<String, dynamic>.from(raw)
        : <String, dynamic>{};
    return WaiterUser.fromJson(user);
  }
}
