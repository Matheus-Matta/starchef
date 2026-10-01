import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/storage/session_store.dart';
import '../domain/auth_session.dart';

/// Renova o access token sem derrubar a sessão de OUTRO processo.
class SessionRefresher {
  SessionRefresher({required this.apiClient, required this.sessionStore});

  final ApiClient apiClient;
  final SessionStore sessionStore;

  /// Troca o refresh token por um novo access token.
  ///
  /// PDV e Balança Rápida são processos separados com a MESMA sessão, e o
  /// backend invalida o refresh antigo a cada renovação. Quem renovava com o
  /// token velho da memória levava 401 e deslogava, apagando do cofre o token
  /// que o outro processo acabara de gravar — o login sumia no próximo início.
  /// Por isso o cofre é relido antes e, de novo, depois de um 401.
  Future<AuthSession> refresh(AuthSession current) async {
    final guardada = await _guardadaDiferente(current);
    try {
      return await _renovar(guardada ?? current);
    } on ApiException catch (error) {
      if (error.statusCode != 401 || guardada != null) rethrow;
      final outra = await _guardadaDiferente(current);
      if (outra == null) rethrow;
      return _renovar(outra);
    }
  }

  Future<AuthSession?> _guardadaDiferente(AuthSession atual) async {
    try {
      final s = await sessionStore.read();
      return s != null && s.refreshToken != atual.refreshToken ? s : null;
    } catch (_) {
      return null;
    }
  }

  Future<AuthSession> _renovar(AuthSession current) async {
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
}
