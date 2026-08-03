import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
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

  /// Troca o refresh token por um novo access token.
  ///
  /// O backend pode rotacionar o refresh; quando isso acontece o novo valor
  /// substitui o anterior no cofre, senão o refresh atual é mantido.
  ///
  /// Lança [ApiException] em vez de devolver `null` porque quem chama precisa
  /// distinguir "o servidor recusou a credencial" de "não deu para falar com o
  /// servidor" — o primeiro caso encerra a sessão, o segundo não pode encerrar.
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
    } catch (_) {
      // Sessão renovada continua válida em memória mesmo sem o cofre.
    }
    return refreshed;
  }

  /// Restaura a sessão guardada no cofre do sistema.
  ///
  /// O access token costuma estar vencido no boot, porque ele vive bem menos
  /// que o intervalo entre dois turnos. Nesse caso a sessão é renovada aqui
  /// mesmo — o `ApiClient` não consegue fazer isso sozinho durante o boot,
  /// pois ainda não existe sessão para ele renovar.
  ///
  /// Sem rede, a sessão guardada é devolvida como está: o terminal precisa
  /// abrir e operar com o cache local.
  Future<AuthSession?> restoreSession() async {
    final stored = await sessionStore.read();
    if (stored == null) return null;
    try {
      return await _identify(stored.accessToken, stored);
    } on ApiException catch (error) {
      if (error.statusCode != 401) return stored;

      // Credencial recusada pelo servidor: vale tentar o refresh guardado.
      try {
        final renewed = await refresh(stored);
        try {
          return await _identify(renewed.accessToken, renewed);
        } on ApiException {
          // O token novo é válido; só não deu para reler o perfil agora.
          await cashAuth?.trySync(renewed);
          return renewed;
        }
      } on ApiException catch (refreshError) {
        if (refreshError.statusCode == null) {
          // A rede caiu entre as duas chamadas. Encerrar a sessão aqui
          // deixaria o terminal sem conseguir entrar de novo, já que o login
          // exige servidor.
          return stored;
        }
        // Recusa definitiva: a credencial guardada não serve mais.
        await sessionStore.clear();
        return null;
      }
    } catch (_) {
      return stored;
    }
  }

  /// Relê o perfil e devolve a sessão com os dados atualizados.
  Future<AuthSession> _identify(String accessToken, AuthSession base) async {
    final userData = await apiClient.get(
      '/auth/me/',
      accessToken: accessToken,
    );
    final session = AuthSession(
      accessToken: accessToken,
      refreshToken: base.refreshToken,
      user: AuthUser.fromJson(userData),
    );
    await sessionStore.save(session);
    // Online: atualiza o hash da senha do caixa guardado no dispositivo.
    await cashAuth?.trySync(session);
    return session;
  }

  Future<void> logout() async {
    await apiClient.clearSession();
    await sessionStore.clear();
    await cashAuth?.clear();
  }
}
