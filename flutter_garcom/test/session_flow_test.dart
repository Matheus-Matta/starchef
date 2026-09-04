import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:starchef_garcom/core/network/api_client.dart';
import 'package:starchef_garcom/core/relay/principal_client.dart';
import 'package:starchef_garcom/core/relay/relay_signature.dart';
import 'package:starchef_garcom/core/storage/session_store.dart';
import 'package:starchef_garcom/features/auth/domain/waiter_session.dart';
import 'package:starchef_garcom/features/auth/presentation/session_controller.dart';

/// Ordem e permanência das duas etapas de entrada.
///
/// As regras que este arquivo protege:
/// 1. O Caixa Principal é configurado DEPOIS do login — o teste de pareamento
///    vai assinado com conta/operador/restaurante, que só existem depois dele.
/// 2. O cadastro do caixa é do APARELHO e acontece uma vez: sair da conta não
///    pode apagá-lo, senão todo fim de turno viraria chamado para o gerente.
/// 3. Dá para trocar o caixa depois, sem deslogar.
void main() {
  late _MemoryStore store;
  late _FakePrincipal principal;
  late SessionController controller;

  const secret = 'chave-de-pareamento';

  setUp(() async {
    store = _MemoryStore();
    principal = _FakePrincipal(secret: secret);
    await principal.start();
    controller = SessionController(
      api: ApiClient(
        baseUrl: 'http://backend.local/api/v1',
        httpClient: _FakeBackend(),
      ),
      principalClient: PrincipalClient(),
      store: store,
    );
  });

  tearDown(() => principal.stop());

  Future<void> login() async {
    final ok = await controller.login(username: 'maria', password: 'x');
    expect(ok, isTrue, reason: controller.error ?? '');
  }

  Future<void> pair({String? host}) async {
    final ok = await controller.pair(
      host: host ?? '127.0.0.1',
      port: '${principal.port}',
      secret: secret,
    );
    expect(ok, isTrue, reason: controller.error ?? '');
  }

  test('aparelho novo começa pedindo login, não o caixa', () async {
    await controller.restore();

    expect(controller.stage, SessionStage.loggedOut);
  });

  test('depois do login, o app pede o caixa', () async {
    await controller.restore();
    await login();

    expect(controller.stage, SessionStage.unpaired);
    expect(controller.principal, isNull);
  });

  test('com login e caixa, o app está pronto para atender', () async {
    await controller.restore();
    await login();
    await pair();

    expect(controller.stage, SessionStage.ready);
    expect(controller.principal?.host, '127.0.0.1');
  });

  test('sair da conta NÃO apaga o caixa configurado', () async {
    await controller.restore();
    await login();
    await pair();

    await controller.logout();

    expect(controller.stage, SessionStage.loggedOut);
    expect(controller.principal, isNotNull, reason: 'pareamento é do aparelho');
    expect(await store.readPrincipal(), isNotNull);
  });

  test('o próximo garçom entra e já cai na lista de pedidos', () async {
    await controller.restore();
    await login();
    await pair();
    await controller.logout();

    await login();

    expect(controller.stage, SessionStage.ready);
  });

  test('o pareamento sobrevive a fechar e abrir o app', () async {
    await controller.restore();
    await login();
    await pair();

    final reaberto = SessionController(
      api: ApiClient(
        baseUrl: 'http://backend.local/api/v1',
        httpClient: _FakeBackend(),
      ),
      principalClient: PrincipalClient(),
      store: store,
    );
    await reaberto.restore();

    expect(reaberto.stage, SessionStage.ready);
    expect(reaberto.principal?.port, principal.port);
  });

  test('trocar o caixa mantém a sessão do garçom', () async {
    await controller.restore();
    await login();
    await pair();
    final antes = controller.session;

    await pair(host: 'localhost');

    expect(controller.session, same(antes));
    expect(controller.principal?.host, 'localhost');
  });

  test('caixa que não responde não é gravado', () async {
    await controller.restore();
    await login();
    await principal.stop();

    final ok = await controller.pair(
      host: '127.0.0.1',
      port: '${principal.port}',
      secret: secret,
    );

    expect(ok, isFalse);
    expect(controller.stage, SessionStage.unpaired);
    expect(await store.readPrincipal(), isNull);
    expect(controller.error, isNotNull);
  });

  test('parear sem estar logado é recusado', () async {
    await controller.restore();

    final ok = await controller.pair(
      host: '127.0.0.1',
      port: '${principal.port}',
      secret: secret,
    );

    expect(ok, isFalse);
    expect(await store.readPrincipal(), isNull);
  });

  test('a identidade do aparelho no relay não muda entre pareamentos', () async {
    await controller.restore();
    await login();
    await pair();
    final primeiro = controller.principal!.nodeId;

    await controller.unpair();
    await pair();

    expect(controller.principal!.nodeId, primeiro);
  });
}

/// Backend de mentira: responde só o login.
class _FakeBackend extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final body = jsonEncode({
      'access': 'token-de-acesso',
      'refresh': 'token-de-renovacao',
      'user': {
        'id': 'garcom-1',
        'username': 'maria',
        'name': 'Maria',
        'account_id': 'conta-1',
        'restaurant_id': 'restaurante-1',
        'restaurant_name': 'Cantina',
        'profile_type': 'waiter',
      },
    });
    return http.StreamedResponse(
      Stream.value(utf8.encode(body)),
      200,
      headers: {'content-type': 'application/json'},
    );
  }
}

/// Caixa Principal de mentira: só o /v1/health assinado, que é o que o
/// pareamento usa.
class _FakePrincipal {
  _FakePrincipal({required this.secret});

  final String secret;
  HttpServer? _server;
  int _port = 0;

  int get port => _port;

  Future<void> start() async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    _server = server;
    _port = server.port;
    server.listen((request) async {
      final nonce = request.headers.value('x-starchef-nonce') ?? '';
      const payload = '{"ok":true}';
      request.response
        ..statusCode = HttpStatus.ok
        ..headers.contentType = ContentType.json
        ..headers.set(
          'x-starchef-response-signature',
          RelaySignature.response(
            secret: secret,
            requestNonce: nonce,
            statusCode: HttpStatus.ok,
            body: payload,
          ),
        )
        ..write(payload);
      await request.response.close();
    });
  }

  Future<void> stop() async {
    await _server?.close(force: true);
    _server = null;
  }
}

class _MemoryStore implements SessionStorage {
  WaiterSession? _session;
  PrincipalConfig? _principal;
  String? _nodeId;

  @override
  Future<WaiterSession?> readSession() async => _session;

  @override
  Future<void> saveSession(WaiterSession session) async => _session = session;

  @override
  Future<void> clearSession() async => _session = null;

  @override
  Future<PrincipalConfig?> readPrincipal() async => _principal;

  @override
  Future<void> savePrincipal(PrincipalConfig config) async =>
      _principal = config;

  @override
  Future<void> clearPrincipal() async => _principal = null;

  @override
  Future<String?> readNodeId() async => _nodeId;

  @override
  Future<void> saveNodeId(String value) async => _nodeId = value;
}
