import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/storage/session_store.dart';
import 'package:starchef_pdv_mobile/features/auth/domain/waiter_session.dart';
import 'package:starchef_pdv_mobile/features/auth/presentation/session_controller.dart';

/// O gerente liga "exigir código do operador" com o garçom JÁ logado. O app
/// restaurava a sessão guardada no login e nunca relia o usuário: seguia sem
/// pedir o código até alguém sair e entrar de novo.
class _Api extends ApiClient {
  _Api() : super(baseUrlProvider: () => 'https://example.test/api/v1');

  bool exige = true;

  @override
  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, dynamic>? query,
    String? accessToken,
  }) async => {
    'id': 'u1',
    'username': 'joao',
    'name': 'João',
    'profile_type': 'waiter',
    'account_id': 'a1',
    'restaurant_id': 'r1',
    'restaurant_name': 'Cobogó',
    'require_operator_code': exige,
  };
}

class _Memoria implements SessionStorage {
  _Memoria(this.sessao);

  WaiterSession? sessao;

  @override
  Future<WaiterSession?> readSession() async => sessao;
  @override
  Future<void> saveSession(WaiterSession session) async => sessao = session;
  @override
  Future<void> clearSession() async => sessao = null;
  @override
  Future<String?> readNodeId() async => 'no-de-teste-123';
  @override
  Future<void> saveNodeId(String value) async {}
}

WaiterSession _logadoSemExigencia() => WaiterSession.fromJson({
  'access': 'a',
  'refresh': 'r',
  'user': {
    'id': 'u1',
    'username': 'joao',
    'name': 'João',
    'profile_type': 'waiter',
    'account_id': 'a1',
    'restaurant_id': 'r1',
    'require_operator_code': false,
  },
});

void main() {
  test('ao abrir o app, a exigência do código vem do servidor, não do login antigo', () async {
    final store = _Memoria(_logadoSemExigencia());
    final controller = SessionController(api: _Api(), store: store);

    await controller.restore();
    await controller.refreshUser();

    expect(controller.session!.user.requireOperatorCode, isTrue);
    expect(store.sessao!.user.requireOperatorCode, isTrue);
    expect(controller.session!.accessToken, 'a');
  });

  test('sem internet a sessão guardada continua valendo', () async {
    final store = _Memoria(_logadoSemExigencia());
    final api = _ApiForaDoAr();
    final controller = SessionController(api: api, store: store);

    await controller.restore();
    await controller.refreshUser();

    expect(controller.session, isNotNull);
    expect(controller.session!.user.requireOperatorCode, isFalse);
  });
}

class _ApiForaDoAr extends ApiClient {
  _ApiForaDoAr() : super(baseUrlProvider: () => 'https://example.test/api/v1');

  @override
  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, dynamic>? query,
    String? accessToken,
  }) async => throw Exception('sem rede');
}
