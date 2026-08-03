import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';
import 'package:starchef_pdv/core/storage/session_store.dart';
import 'package:starchef_pdv/features/auth/data/auth_repository.dart';
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
    final api = clientWith(
      MockClient((_) async => http.Response('{}', 200)),
    );
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
}
