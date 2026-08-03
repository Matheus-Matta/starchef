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
  String? errorMessage;

  /// Mensagem mostrada na tela de login quando a sessão caiu sozinha.
  String? expiredNotice;

  bool _disposed = false;

  bool get isAuthenticated => session != null;
  AuthRepository get repository => _repository;

  Future<void> initialize() async {
    // A restauração renova o token por conta própria quando necessário, então
    // o refresher do ApiClient só é ligado depois: durante o boot ainda não há
    // sessão em memória para ele renovar.
    session = await _repository.restoreSession();
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
      session = await _repository.login(
        username: username,
        password: password,
        remember: remember,
      );
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
      errorMessage = 'Ocorreu um erro inesperado. Tente novamente.';
      return false;
    } finally {
      loading = false;
      _safeNotify();
    }
  }

  Future<void> logout() async {
    await _repository.logout();
    session = null;
    expiredNotice = null;
    _safeNotify();
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
