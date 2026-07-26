import 'package:flutter/foundation.dart';

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

  bool get isAuthenticated => session != null;
  AuthRepository get repository => _repository;

  Future<void> initialize() async {
    session = await _repository.restoreSession();
    initialized = true;
    notifyListeners();
  }

  Future<bool> login({
    required String username,
    required String password,
    required bool remember,
  }) async {
    loading = true;
    errorMessage = null;
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
    } catch (_) {
      errorMessage = 'Ocorreu um erro inesperado. Tente novamente.';
      return false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    await _repository.logout();
    session = null;
    notifyListeners();
  }
}
