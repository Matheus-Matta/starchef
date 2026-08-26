import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/relay/principal_client.dart';
import '../../../core/relay/relay_signature.dart';
import '../../../core/storage/session_store.dart';
import '../domain/waiter_session.dart';

/// Os dois passos da entrada, separados de propósito.
///
/// 1. [login] — quem é o garçom. Só o backend responde isso, e é dele que saem
///    conta e restaurante.
/// 2. [pair] — para qual Caixa Principal vão os pedidos. Depende do passo 1:
///    a requisição ao principal vai assinada com conta, operador e restaurante,
///    que só existem depois do login.
class AuthRepository {
  AuthRepository({
    required this.api,
    required this.principalClient,
    required this.store,
  });

  final ApiClient api;
  final PrincipalClient principalClient;
  final SessionStorage store;

  Future<WaiterSession> login({
    required String username,
    required String password,
  }) async {
    final json = await api.post(
      '/auth/login/',
      // App nativo usa Bearer, não os cookies httpOnly do navegador.
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
        'Seu usuário não está vinculado a um restaurante. Peça ao '
        'responsável para ajustar o cadastro antes de usar o app.',
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

  /// Testa o pareamento com o Caixa Principal e só grava se ele responder.
  ///
  /// Gravar antes de testar deixaria o garçom achando que está pronto para
  /// atender e descobrindo o erro na primeira mesa.
  Future<PrincipalConfig> pair({
    required WaiterSession session,
    required String host,
    required int port,
    required String secret,
  }) async {
    final config = PrincipalConfig(
      host: host.trim(),
      port: port,
      secret: secret.trim(),
      nodeId: await _nodeId(),
    );
    final errors = config.validate();
    if (errors.isNotEmpty) throw ApiException(errors.join(' '));

    if (!await principalClient.health(config, session.identity)) {
      throw const ApiException(
        'O Caixa Principal respondeu, mas recusou o pareamento.',
      );
    }

    await store.savePrincipal(config);
    return config;
  }

  /// Sai da sessão do garçom mantendo o pareamento: o aparelho continua sendo
  /// daquela loja, e o próximo turno não precisa do gerente para reconfigurar.
  Future<void> logout() => store.clearSession();

  Future<String> _nodeId() async {
    final saved = await store.readNodeId();
    if (saved != null && saved.trim().length >= 8) return saved;
    final generated = RelaySignature.randomId();
    await store.saveNodeId(generated);
    return generated;
  }

  static WaiterUser _userFrom(Map<String, dynamic> json) {
    final raw = json['user'];
    final user = raw is Map
        ? Map<String, dynamic>.from(raw)
        : <String, dynamic>{};
    return WaiterUser(
      id: '${user['id'] ?? ''}',
      username: '${user['username'] ?? ''}',
      name: '${user['name'] ?? ''}',
      accountId: '${user['account_id'] ?? ''}',
      restaurantId: '${user['restaurant_id'] ?? ''}',
      restaurantName: '${user['restaurant_name'] ?? ''}',
      profileType: '${user['profile_type'] ?? ''}',
    );
  }
}
