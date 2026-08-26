import 'package:flutter/foundation.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/relay/principal_client.dart';
import '../../../core/storage/session_store.dart';
import '../data/auth_repository.dart';
import '../domain/waiter_session.dart';

/// Em que ponto da entrada o app está. É o que decide a tela.
enum SessionStage {
  /// Lendo o cofre do aparelho.
  restoring,

  /// Ninguém logado.
  loggedOut,

  /// Logado, mas o aparelho ainda não sabe para qual caixa mandar o pedido.
  unpaired,

  /// Pronto para atender.
  ready,
}

class SessionController extends ChangeNotifier {
  SessionController({
    required this.api,
    required this.principalClient,
    required this.store,
  }) : _repository = AuthRepository(
         api: api,
         principalClient: principalClient,
         store: store,
       );

  final ApiClient api;
  final PrincipalClient principalClient;
  final SessionStorage store;
  final AuthRepository _repository;

  WaiterSession? _session;
  PrincipalConfig? _principal;
  bool _restoring = true;
  bool _loading = false;
  String? _error;

  WaiterSession? get session => _session;
  PrincipalConfig? get principal => _principal;
  bool get loading => _loading;
  String? get error => _error;

  SessionStage get stage {
    if (_restoring) return SessionStage.restoring;
    if (_session == null) return SessionStage.loggedOut;
    if (_principal == null) return SessionStage.unpaired;
    return SessionStage.ready;
  }

  Future<void> restore() async {
    // O pareamento é do aparelho: é lido mesmo sem sessão, para o garçom
    // seguinte cair direto na lista de pedidos depois de entrar.
    final restored = await store.readSession();
    if (restored != null && restored.user.profileType != 'waiter') {
      // Versões antigas aceitavam a mesma sessão do PDV. Não restaura essa
      // credencial depois que o app passou a exigir uma conta de garçom.
      await store.clearSession();
      _session = null;
    } else {
      _session = restored;
    }
    _principal = await store.readPrincipal();
    _restoring = false;
    notifyListeners();
  }

  Future<bool> login({required String username, required String password}) =>
      _run(() async {
        _session = await _repository.login(
          username: username,
          password: password,
        );
      });

  Future<bool> pair({
    required String host,
    required String port,
    required String secret,
  }) {
    final current = _session;
    if (current == null) {
      _error = 'Entre com seu usuário antes de configurar o caixa.';
      notifyListeners();
      return Future.value(false);
    }
    return _run(() async {
      _principal = await _repository.pair(
        session: current,
        host: host,
        port: port.trim().isEmpty
            ? PrincipalConfig.defaultPort
            : int.tryParse(port.trim()) ?? PrincipalConfig.defaultPort,
        secret: secret,
      );
    });
  }

  /// Sai da sessão mantendo o pareamento (ver [AuthRepository.logout]).
  Future<void> logout() async {
    await _repository.logout();
    _session = null;
    _error = null;
    notifyListeners();
  }

  /// Esquece o caixa pareado — usado quando a loja troca o computador do
  /// caixa ou gera uma chave nova.
  Future<void> unpair() async {
    await store.clearPrincipal();
    _principal = null;
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
    } on PrincipalUnavailable catch (error) {
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
