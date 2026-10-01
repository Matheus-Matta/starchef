import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/storage/session_store.dart';
import '../data/auth_repository.dart';
import '../domain/waiter_session.dart';

enum SessionStage { restoring, loggedOut, ready }

class SessionController extends ChangeNotifier {
  SessionController({required this.api, required this.store})
    : _repository = AuthRepository(api: api, store: store);

  final ApiClient api;
  final SessionStorage store;
  final AuthRepository _repository;

  WaiterSession? _session;
  bool _restoring = true;
  bool _loading = false;
  String? _error;

  WaiterSession? get session => _session;
  bool get loading => _loading;
  String? get error => _error;
  SessionStage get stage => _restoring
      ? SessionStage.restoring
      : _session == null
      ? SessionStage.loggedOut
      : SessionStage.ready;

  Future<void> restore() async {
    final restored = await store.readSession();
    if (restored != null && restored.user.profileType != 'waiter') {
      await store.clearSession();
    } else {
      _session = restored;
      if (restored != null) await _configureApi(restored);
    }
    _restoring = false;
    notifyListeners();
    unawaited(refreshUser());
  }

  /// Relê o usuário no servidor e atualiza a sessão guardada.
  ///
  /// O login grava junto as EXIGÊNCIAS do restaurante (código do operador).
  /// Sem reler, uma configuração ligada com o garçom já logado só valia depois
  /// de sair e entrar de novo. Sem rede, segue com o que estava guardado: o
  /// atendimento não pode parar por isso.
  Future<void> refreshUser() async {
    if (_session == null) return;
    try {
      final user = await _repository.fetchUser();
      final atual = _session;
      if (atual == null ||
          user.id != atual.user.id ||
          user.restaurantId.isEmpty) {
        return;
      }
      _session = atual.withUser(user);
      await store.saveSession(_session!);
      notifyListeners();
    } catch (_) {
      // Sem rede ou servidor fora: a sessão guardada continua valendo.
    }
  }

  Future<bool> login({required String username, required String password}) =>
      _run(() async {
        final session = await _repository.login(
          username: username,
          password: password,
        );
        _session = session;
        await _configureApi(session);
      });

  Future<void> _configureApi(WaiterSession session) async {
    api.configureSession(
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
      terminalId: await _repository.nodeId(),
      onTokensChanged: (access, refresh) async {
        final current = _session;
        if (current == null) return;
        _session = current.withTokens(access, refresh);
        await store.saveSession(_session!);
      },
    );
  }

  Future<void> logout() async {
    await _repository.logout();
    api.clearSession();
    _session = null;
    _error = null;
    notifyListeners();
  }

  void clearError() {
    if (_error == null) return;
    _error = null;
    notifyListeners();
  }

  Future<bool> _run(Future<void> Function() action) async {
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      await action();
      return true;
    } on ApiException catch (error) {
      _error = error.message;
      return false;
    } catch (error) {
      _error = 'Falha inesperada: $error';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }
}
