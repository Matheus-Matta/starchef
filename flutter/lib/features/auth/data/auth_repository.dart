import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/storage/durable_secure_store.dart';
import '../../../core/storage/session_store.dart';
import '../../cash/data/cash_auth_repository.dart';
import '../domain/auth_session.dart';
import 'offline_login_store.dart';

class AuthLoginResult {
  const AuthLoginResult({required this.session, required this.offline});

  final AuthSession session;
  final bool offline;
}

class AuthRepository {
  AuthRepository({
    required this.apiClient,
    required this.sessionStore,
    this.cashAuth,
    OfflineLoginStore? offlineLoginStore,
    SecureValueStore? credentials,
  }) : offlineLoginStore = offlineLoginStore ?? SecureOfflineLoginStore(),
       credentials = credentials ?? DurableSecureStore();

  final ApiClient apiClient;
  final SessionStore sessionStore;
  final OfflineLoginStore offlineLoginStore;

  /// Camadas duráveis onde as credenciais deste terminal ficam.
  ///
  /// Exposto para quem guarda outro segredo com a mesma exigência — a chave de
  /// pareamento do Caixa Principal —, para que todas usem o mesmo conjunto de
  /// camadas em vez de cada uma montar o seu.
  final SecureValueStore credentials;

  // Sincroniza/guarda o hash da senha de ações do caixa para uso offline.
  final CashAuthRepository? cashAuth;

  /// Valida no servidor um administrador da mesma conta sem substituir a
  /// sessão atual do operador e sem guardar as credenciais informadas.
  Future<void> authorizeAdministrator({
    required AuthSession currentSession,
    required String username,
    required String password,
    String? requiredPermission,
  }) async {
    await apiClient.post(
      '/auth/authorize-admin/',
      accessToken: currentSession.accessToken,
      body: {
        'username': username.trim(),
        'password': password,
        'permission': ?requiredPermission,
      },
    );
  }

  /// Compatibilidade para consumidores que só precisam da sessão.
  Future<AuthSession> login({
    required String username,
    required String password,
    required bool remember,
  }) async => (await loginWithFallback(
    username: username,
    password: password,
    remember: remember,
  )).session;

  /// Tenta sempre o servidor primeiro e usa o verificador local apenas quando
  /// a falha é de conectividade. Uma resposta 401 nunca cai no cache.
  Future<AuthLoginResult> loginWithFallback({
    required String username,
    required String password,
    required bool remember,
  }) async {
    late final AuthSession session;
    try {
      final json = await apiClient.post(
        '/auth/login/',
        // App nativo usa token Bearer, não cookies HttpOnly do navegador.
        body: {
          'username': username.trim(),
          'password': password,
          'no_cookie': true,
        },
      );
      session = AuthSession.fromJson(json);
    } on ApiException catch (error) {
      if (!error.isConnectivity) rethrow;
      final cached = await offlineLoginStore.authenticate(
        username: username,
        password: password,
      );
      if (cached == null) {
        throw const ApiException(
          'Sem conexão com a Retaguarda e não há credenciais offline válidas para este usuário. Conecte este terminal à internet e faça um login bem-sucedido primeiro.',
          isConnectivity: true,
        );
      }
      if (remember) {
        try {
          await sessionStore.save(cached).timeout(const Duration(seconds: 5));
        } catch (_) {}
      }
      return AuthLoginResult(session: cached, offline: true);
    }

    if (remember) {
      // A sessão autenticada continua válida em memória mesmo se o cofre do
      // Windows estiver temporariamente indisponível.
      try {
        await sessionStore.save(session).timeout(const Duration(seconds: 5));
      } catch (_) {}
    }

    // O cache de credenciais é requisito operacional e independe de
    // "Lembrar-me": essa opção controla somente a restauração automática da
    // sessão. Falha do cofre não invalida o login online já autorizado.
    try {
      await offlineLoginStore
          .save(username: username, password: password, session: session)
          .timeout(const Duration(seconds: 12));
    } catch (_) {}

    // Baixa e guarda o hash da senha do caixa (para autorização offline).
    await cashAuth?.trySync(session);
    return AuthLoginResult(session: session, offline: false);
  }

  /// Troca o refresh token por um novo access token.
  Future<AuthSession> refresh(AuthSession current) async {
    final json = await apiClient.post(
      '/auth/refresh/',
      body: {'refresh': current.refreshToken, 'no_cookie': true},
    );
    final access = '${json['access'] ?? ''}';
    if (access.isEmpty) {
      throw const ApiException(
        'O servidor não devolveu um novo token de acesso.',
        statusCode: 401,
      );
    }
    final refreshed = AuthSession(
      accessToken: access,
      refreshToken: '${json['refresh'] ?? ''}'.isEmpty
          ? current.refreshToken
          : '${json['refresh']}',
      user: current.user,
    );
    try {
      await sessionStore.save(refreshed).timeout(const Duration(seconds: 5));
    } catch (_) {}
    return refreshed;
  }

  /// Restaura a sessão guardada no cofre do sistema.
  Future<AuthSession?> restoreSession() async =>
      (await restoreSessionWithStatus())?.session;

  /// Também informa se a restauração ocorreu sem alcançar a Retaguarda.
  Future<AuthLoginResult?> restoreSessionWithStatus() async {
    final stored = await sessionStore.read();
    if (stored == null) return null;
    try {
      return AuthLoginResult(
        session: await _identify(stored.accessToken, stored),
        offline: false,
      );
    } on ApiException catch (error) {
      if (error.statusCode != 401) {
        return AuthLoginResult(session: stored, offline: error.isConnectivity);
      }

      // Credencial recusada pelo servidor: vale tentar o refresh guardado.
      try {
        final renewed = await refresh(stored);
        try {
          return AuthLoginResult(
            session: await _identify(renewed.accessToken, renewed),
            offline: false,
          );
        } on ApiException catch (identifyError) {
          // O token novo é válido; só não deu para reler o perfil agora.
          await cashAuth?.trySync(renewed);
          return AuthLoginResult(
            session: renewed,
            offline: identifyError.isConnectivity,
          );
        }
      } on ApiException catch (refreshError) {
        if (refreshError.statusCode == null) {
          return AuthLoginResult(session: stored, offline: true);
        }
        // Recusa definitiva: a credencial guardada não serve mais.
        await sessionStore.clear();
        return null;
      }
    } catch (_) {
      return AuthLoginResult(session: stored, offline: true);
    }
  }

  /// Relê o perfil e devolve a sessão com os dados atualizados.
  Future<AuthSession> _identify(String accessToken, AuthSession base) async {
    final userData = await apiClient.get('/auth/me/', accessToken: accessToken);
    final session = AuthSession(
      accessToken: accessToken,
      refreshToken: base.refreshToken,
      user: AuthUser.fromJson(userData),
    );
    await sessionStore.save(session);
    await cashAuth?.trySync(session);
    return session;
  }

  Future<void> logout() async {
    await apiClient.clearSession();
    await sessionStore.clear();
    await cashAuth?.clear();
    // O verificador de login offline permanece no cofre: o próximo operador
    // precisa conseguir entrar se a internet cair depois deste logout.
  }
}
