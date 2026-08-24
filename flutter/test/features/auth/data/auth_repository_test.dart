import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';
import 'package:starchef_pdv/core/storage/session_store.dart';
import 'package:starchef_pdv/features/auth/data/auth_repository.dart';
import 'package:starchef_pdv/features/auth/data/offline_login_store.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';

/// Cofre em memória, para não tocar no cofre real do sistema.
class FakeSessionStore implements SessionStore {
  FakeSessionStore([this.stored]);

  AuthSession? stored;
  int clears = 0;
  int saves = 0;

  @override
  Future<AuthSession?> read() async => stored;

  @override
  Future<void> save(AuthSession session) async {
    saves += 1;
    stored = session;
  }

  @override
  Future<void> clear() async {
    clears += 1;
    stored = null;
  }
}

class FakeOfflineLoginStore implements OfflineLoginStore {
  AuthSession? session;
  String? username;
  String? password;
  int saves = 0;
  int authenticationAttempts = 0;

  @override
  Future<void> save({
    required String username,
    required String password,
    required AuthSession session,
  }) async {
    saves += 1;
    this.username = username.trim().toLowerCase();
    this.password = password;
    this.session = session;
  }

  @override
  Future<AuthSession?> authenticate({
    required String username,
    required String password,
  }) async {
    authenticationAttempts += 1;
    return username.trim().toLowerCase() == this.username &&
            password == this.password
        ? session
        : null;
  }
}

AuthSession sessionWith({
  String access = 'access-antigo',
  String refresh = 'refresh-valido',
}) => AuthSession(
  accessToken: access,
  refreshToken: refresh,
  user: const AuthUser(id: 'u1', username: 'ana', name: 'Ana'),
);

String userJson() => jsonEncode({
  'id': 'u1',
  'username': 'ana',
  'name': 'Ana Souza',
  'account_id': 'acc-1',
});

void main() {
  late Directory directory;
  late int offlineFileCounter;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-auth');
    offlineFileCounter = 0;
  });

  tearDown(() async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // O arquivo pode continuar preso por instantes no Windows.
    }
  });

  /// Cada cliente recebe seu próprio banco offline para não compartilhar fila.
  ApiClient clientWith(http.Client transport) {
    offlineFileCounter += 1;
    return ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: transport,
      offlineStore: OfflineStore(
        file: File(
          '${directory.path}${Platform.pathSeparator}'
          'offline-$offlineFileCounter.sqlite',
        ),
      ),
    );
  }

  test('token vencido é renovado durante a restauração', () async {
    final calls = <String>[];
    final api = clientWith(
      MockClient((request) async {
        calls.add('${request.method} ${request.url.path}');
        if (request.url.path.endsWith('/auth/refresh/')) {
          return http.Response(
            jsonEncode({'access': 'access-novo'}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        // O `/auth/me/` só aceita o token renovado.
        final authorized =
            request.headers['Authorization'] == 'Bearer access-novo';
        return http.Response(
          authorized
              ? userJson()
              : jsonEncode({'detail': 'Credencial inválida ou expirada.'}),
          authorized ? 200 : 401,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    final store = FakeSessionStore(sessionWith());
    final repository = AuthRepository(apiClient: api, sessionStore: store);

    final restored = await repository.restoreSession();

    expect(restored, isNotNull);
    expect(restored!.accessToken, 'access-novo');
    expect(restored.user.name, 'Ana Souza');
    // O refresh foi tentado apenas depois da recusa do perfil.
    expect(calls, [
      'GET /api/v1/auth/me/',
      'POST /api/v1/auth/refresh/',
      'GET /api/v1/auth/me/',
    ]);
    expect(store.clears, 0);
    await api.dispose();
  });

  test('refresh recusado encerra a sessão e limpa o cofre', () async {
    final api = clientWith(
      MockClient(
        (_) async => http.Response(
          jsonEncode({'detail': 'Token inválido.'}),
          401,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    final store = FakeSessionStore(sessionWith());
    final repository = AuthRepository(apiClient: api, sessionStore: store);

    final restored = await repository.restoreSession();

    expect(restored, isNull);
    expect(store.clears, 1);
    expect(store.stored, isNull);
    await api.dispose();
  });

  test('sem rede a sessão guardada é preservada para operar offline', () async {
    final api = clientWith(
      MockClient((_) async => throw const SocketException('sem rota')),
    );
    final store = FakeSessionStore(sessionWith());
    final repository = AuthRepository(apiClient: api, sessionStore: store);

    final restored = await repository.restoreSession();

    // Encerrar a sessão aqui deixaria o terminal sem conseguir entrar de novo,
    // já que o login exige servidor.
    expect(restored, isNotNull);
    expect(restored!.accessToken, 'access-antigo');
    expect(store.clears, 0);
    await api.dispose();
  });

  test('queda de rede entre a recusa e o refresh não desloga', () async {
    var seenProfile = false;
    final api = clientWith(
      MockClient((request) async {
        if (request.url.path.endsWith('/auth/me/') && !seenProfile) {
          seenProfile = true;
          return http.Response(
            jsonEncode({'detail': 'Credencial inválida ou expirada.'}),
            401,
            headers: {'content-type': 'application/json'},
          );
        }
        throw const SocketException('a rede caiu no meio');
      }),
    );
    final store = FakeSessionStore(sessionWith());
    final repository = AuthRepository(apiClient: api, sessionStore: store);

    final restored = await repository.restoreSession();

    expect(restored, isNotNull);
    expect(store.clears, 0);
    await api.dispose();
  });

  test('sem sessão guardada não há o que restaurar', () async {
    final api = clientWith(MockClient((_) async => http.Response('{}', 200)));
    final repository = AuthRepository(
      apiClient: api,
      sessionStore: FakeSessionStore(),
    );

    expect(await repository.restoreSession(), isNull);
    await api.dispose();
  });

  test('refresh sem access token na resposta é tratado como recusa', () async {
    final api = clientWith(
      MockClient(
        (request) async => request.url.path.endsWith('/auth/refresh/')
            ? http.Response(
                jsonEncode({'detail': 'ok mas vazio'}),
                200,
                headers: {'content-type': 'application/json'},
              )
            : http.Response(
                jsonEncode({'detail': 'expirado'}),
                401,
                headers: {'content-type': 'application/json'},
              ),
      ),
    );
    final store = FakeSessionStore(sessionWith());
    final repository = AuthRepository(apiClient: api, sessionStore: store);

    expect(await repository.restoreSession(), isNull);
    expect(store.clears, 1);
    await api.dispose();
  });

  test('login online atualiza o cache seguro mesmo sem Lembrar-me', () async {
    final api = clientWith(
      MockClient(
        (_) async => http.Response(
          jsonEncode({
            'access': 'access-novo',
            'refresh': 'refresh-novo',
            'user': {'id': 'u1', 'username': 'ana', 'name': 'Ana'},
          }),
          200,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    final sessions = FakeSessionStore();
    final offline = FakeOfflineLoginStore();
    final repository = AuthRepository(
      apiClient: api,
      sessionStore: sessions,
      offlineLoginStore: offline,
    );

    final result = await repository.loginWithFallback(
      username: 'Ana',
      password: 'segredo',
      remember: false,
    );

    expect(result.offline, isFalse);
    expect(offline.saves, 1);
    expect(offline.username, 'ana');
    expect(sessions.saves, 0);
    await api.dispose();
  });

  test(
    'timeout no servidor valida usuário e senha contra o cache local',
    () async {
      final api = clientWith(
        MockClient((_) async => throw const SocketException('sem internet')),
      );
      final cached = sessionWith();
      final offline = FakeOfflineLoginStore()
        ..username = 'ana'
        ..password = 'segredo'
        ..session = cached;
      final repository = AuthRepository(
        apiClient: api,
        sessionStore: FakeSessionStore(),
        offlineLoginStore: offline,
      );

      final result = await repository.loginWithFallback(
        username: 'ANA',
        password: 'segredo',
        remember: false,
      );

      expect(result.offline, isTrue);
      expect(result.session, same(cached));
      expect(offline.authenticationAttempts, 1);
      await api.dispose();
    },
  );

  test('senha recusada pelo servidor nunca usa o cache offline', () async {
    final api = clientWith(
      MockClient(
        (_) async => http.Response(
          jsonEncode({'detail': 'Credenciais inválidas.'}),
          401,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    final offline = FakeOfflineLoginStore()
      ..username = 'ana'
      ..password = 'segredo'
      ..session = sessionWith();
    final repository = AuthRepository(
      apiClient: api,
      sessionStore: FakeSessionStore(),
      offlineLoginStore: offline,
    );

    expect(
      () => repository.loginWithFallback(
        username: 'ana',
        password: 'errada',
        remember: false,
      ),
      throwsA(
        isA<ApiException>().having((error) => error.statusCode, 'status', 401),
      ),
    );
    expect(offline.authenticationAttempts, 0);
    await api.dispose();
  });

  test('autorização administrativa usa a API sem trocar a sessão', () async {
    late http.Request received;
    final api = clientWith(
      MockClient((request) async {
        received = request;
        return http.Response(
          jsonEncode({'authorized': true}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    final repository = AuthRepository(
      apiClient: api,
      sessionStore: FakeSessionStore(),
    );
    final current = sessionWith(access: 'token-operador');

    await repository.authorizeAdministrator(
      currentSession: current,
      username: ' admin@starchef.test ',
      password: 'senha-admin',
    );

    expect(received.url.path, '/api/v1/auth/authorize-admin/');
    expect(received.headers['Authorization'], 'Bearer token-operador');
    expect(jsonDecode(received.body), {
      'username': 'admin@starchef.test',
      'password': 'senha-admin',
    });
    expect(current.accessToken, 'token-operador');
    await api.dispose();
  });

  test('autoriza cancelamento com a permissão específica do pedido', () async {
    late http.Request received;
    final api = clientWith(
      MockClient((request) async {
        received = request;
        return http.Response('{"authorized":true}', 200);
      }),
    );
    final repository = AuthRepository(
      apiClient: api,
      sessionStore: FakeSessionStore(),
    );

    await repository.authorizeAdministrator(
      currentSession: sessionWith(access: 'token-operador'),
      username: 'gerente',
      password: 'senha',
      requiredPermission: 'orders.cancel',
    );

    expect(jsonDecode(received.body)['permission'], 'orders.cancel');
    await api.dispose();
  });
}
