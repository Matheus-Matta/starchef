import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_exception.dart';
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
