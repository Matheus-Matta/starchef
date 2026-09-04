import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/security/app_close_password.dart';
import '../data/auth_repository.dart';
import '../domain/auth_session.dart';

class AuthController extends ChangeNotifier {
  AuthController(this._repository);

  final AuthRepository _repository;
  AuthSession? session;
  bool loading = false;
  bool initialized = false;
  bool offlineMode = false;
  String? errorMessage;
  String? activeRestaurantId;

  /// Mensagem mostrada na tela de login quando a sessão caiu sozinha.
  String? expiredNotice;

  bool _disposed = false;

  bool get isAuthenticated => session != null;
  AuthRepository get repository => _repository;
  String get apiBaseUrl => _repository.apiClient.baseUrl;

  Future<void> updateApiBaseUrl(String value) =>
      _repository.apiClient.updateBaseUrl(value);

  /// Usada somente antes do login, quando ainda não há restaurante nem
  /// credenciais administrativas disponíveis para autorizar o fechamento.
  Future<bool> verifyLoginClosePassword(String password) =>
      AppClosePassword.verify(password);

  Future<void> initialize() async {
    // A restauração renova o token por conta própria quando necessário, então
    // o refresher do ApiClient só é ligado depois: durante o boot ainda não há
    // sessão em memória para ele renovar.
    final restored = await _repository.restoreSessionWithStatus();
    session = restored?.session;
    offlineMode = restored?.offline ?? false;
    _repository.apiClient.attachTokenRefresher(_renewAccessToken);
    initialized = true;
    _safeNotify();
  }

  Future<String?> _renewAccessToken() async {
    final current = session;
    if (current == null) return null;
    try {
      final renewed = await _repository.refresh(current);
      session = renewed;
      AppLogger.instance.info('auth_refresh_ok');
      _safeNotify();
      return renewed.accessToken;
    } on ApiException catch (error) {
      AppLogger.instance.warning(
        'auth_refresh_failed',
        data: {'status': error.statusCode},
      );
      // Sem resposta do servidor a sessão continua válida: quem falhou foi a
      // renovação, e a operação offline não pode ser interrompida por isso.
      // Uma recusa explícita, ao contrário, encerra a sessão.
      if (error.statusCode != null) _handleSessionExpired();
      return null;
    }
  }

  void _handleSessionExpired() {
    if (session == null) return;
    session = null;
    offlineMode = false;
    expiredNotice =
        'Sua sessão expirou. Entre novamente para continuar operando.';
    AppLogger.instance.warning('auth_session_expired');
    // A fila offline permanece intacta: o logout aqui é apenas da credencial.
    unawaited(_repository.logout());
    _safeNotify();
  }

  Future<bool> login({
    required String username,
    required String password,
    required bool remember,
  }) async {
    loading = true;
    errorMessage = null;
    expiredNotice = null;
    notifyListeners();
    try {
      final result = await _repository.loginWithFallback(
        username: username,
        password: password,
        remember: remember,
      );
      session = result.session;
      offlineMode = result.offline;
      return true;
    } on ApiException catch (error) {
      errorMessage = error.message;
      return false;
    } catch (error, stackTrace) {
      AppLogger.instance.error(
        'auth_login_failed',
        cause: error,
        stackTrace: stackTrace,
      );
      // Não deveria chegar aqui — falhas de rede já viram ApiException em
      // ApiClient. Mas se algo inesperado escapar, mostrar só "erro
      // inesperado" sem detalhe nenhum torna impossível diagnosticar sem
      // acesso ao log do terminal. Inclui o texto da exceção.
      errorMessage = 'Ocorreu um erro inesperado ao entrar: $error';
      return false;
    } finally {
      loading = false;
      _safeNotify();
    }
  }

  Future<void> logout() async {
    await _repository.logout();
    session = null;
    offlineMode = false;
    activeRestaurantId = null;
    expiredNotice = null;
    _safeNotify();
  }

  void setActiveRestaurant(String? restaurantId) {
    activeRestaurantId = restaurantId;
  }

  /// Remove o aviso de autenticação offline assim que a Retaguarda volta.
  void markOnline() {
    if (!offlineMode) return;
    offlineMode = false;
    _safeNotify();
  }

  /// Confere a senha cadastrada do restaurante; enquanto ainda não houver um
  /// hash sincronizado, aceita a senha temporária definida pelo produto.
  Future<bool> verifySupervisorClosePassword(String password) async {
    final restaurantId = activeRestaurantId ?? session?.user.restaurantId;
    final cashAuth = _repository.cashAuth;
    if (restaurantId != null && restaurantId.isNotEmpty && cashAuth != null) {
      final hasStored = await cashAuth.hasStoredPassword(restaurantId);
      if (hasStored) {
        return cashAuth.verify(password, restaurantId: restaurantId);
      }
    }
    return password == '12345678';
  }

  /// Rebaixa o hash mais recente da senha do restaurante para a memória e para
  /// o cofre criptografado do sistema. Retorna false quando não há rede.
  Future<bool> refreshSupervisorPassword({String? restaurantId}) async {
    final current = session;
    final cashAuth = _repository.cashAuth;
    restaurantId ??= activeRestaurantId ?? current?.user.restaurantId;
    if (current == null ||
        cashAuth == null ||
        restaurantId == null ||
        restaurantId.isEmpty) {
      return false;
    }
    return cashAuth.trySync(current, restaurantId: restaurantId);
  }

  /// Valida online credenciais administrativas da mesma conta. `null`
  /// significa autorização aprovada; qualquer texto é seguro para a UI.
  Future<String?> verifyAdministratorCloseCredentials(
    String username,
    String password,
  ) async {
    final current = session;
    if (current == null) return 'A sessão atual não está disponível.';
    try {
      await _repository.authorizeAdministrator(
        currentSession: current,
        username: username,
        password: password,
      );
      return null;
    } on ApiException catch (error) {
      if (error.isConnectivity) {
        return 'A validação do administrador exige conexão com a Retaguarda. '
            'Use a senha do restaurante para autorizar offline.';
      }
      return error.message;
    } catch (_) {
      return 'Não foi possível validar o administrador.';
    }
  }

  /// Autoriza o cancelamento com um administrador ou um usuário da mesma
  /// conta que possua explicitamente `orders.cancel`.
  Future<String?> verifyOrderCancellationCredentials(
    String username,
    String password,
  ) async {
    final current = session;
    if (current == null) return 'A sessão atual não está disponível.';
    try {
      await _repository.authorizeAdministrator(
        currentSession: current,
        username: username,
        password: password,
        requiredPermission: 'orders.cancel',
      );
      return null;
    } on ApiException catch (error) {
      if (error.isConnectivity) {
        return 'A validação por login exige conexão com a Retaguarda. '
            'Use a senha de operação do restaurante.';
      }
      return error.message;
    } catch (_) {
      return 'Não foi possível validar o usuário autorizado.';
    }
  }

  void _safeNotify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _repository.apiClient.attachTokenRefresher(null);
    super.dispose();
  }
}
