import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/auth/data/auth_repository.dart';
import 'package:starchef_pdv_desktop/features/auth/presentation/auth_controller.dart';

import 'data/auth_repository_test.dart' show FakeSessionStore, sessionWith;

http.Response _json(Object body, int status) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json'},
);

ApiClient _clientWith(Future<http.Response> Function(http.Request) handler) =>
    ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient(handler),
    );

void main() {
  for (final status in [429, 500, 502, 503, 504]) {
    test(
      'refresh respondido com $status no boot não apaga o login guardado',
      () async {
        // Depois de reiniciar o PC, o PDV abre antes de o backend da loja
        // terminar de subir: o proxy responde 502/503 e o access token da
        // véspera já venceu. Tratar esse status como recusa apagava o cofre e
        // o operador tinha que entrar de novo a cada reinício.
        final api = _clientWith(
          (request) async => request.url.path.endsWith('/auth/refresh/')
              ? _json({'detail': 'indisponível'}, status)
              : _json({'detail': 'expirado'}, 401),
        );
        final store = FakeSessionStore(sessionWith());
        final repository = AuthRepository(apiClient: api, sessionStore: store);

        final restored = await repository.restoreSessionWithStatus();

        expect(restored, isNotNull);
        expect(restored!.session.refreshToken, 'refresh-valido');
        expect(store.clears, 0);
        await api.dispose();
      },
    );
  }

  test(
    'renovação em uso que recebe 503 mantém a sessão e o cofre intactos',
    () async {
      // O mesmo defeito com o PDV já aberto: qualquer status na renovação
      // derrubava a sessão. Só a recusa do token (401) encerra o login.
      final api = _clientWith(
        (request) async => request.url.path.endsWith('/auth/refresh/')
            ? _json({'detail': 'subindo'}, 503)
            : _json({'detail': 'expirado'}, 401),
      );
      final store = FakeSessionStore();
      final controller = AuthController(
        AuthRepository(apiClient: api, sessionStore: store),
      );
      await controller.initialize();
      controller.session = sessionWith();

      await expectLater(
        api.get('/orders/', accessToken: 'access-antigo'),
        throwsA(anything),
      );

      expect(controller.session, isNotNull);
      expect(controller.expiredNotice, isNull);
      expect(store.clears, 0);
      controller.dispose();
      await api.dispose();
    },
  );

  test('renovação recusada com 401 continua encerrando a sessão', () async {
    final api = _clientWith((_) async => _json({'detail': 'inválido'}, 401));
    final store = FakeSessionStore();
    final controller = AuthController(
      AuthRepository(apiClient: api, sessionStore: store),
    );
    await controller.initialize();
    controller.session = sessionWith();

    await expectLater(
      api.get('/orders/', accessToken: 'access-antigo'),
      throwsA(anything),
    );
    await Future<void>.delayed(Duration.zero);

    expect(controller.session, isNull);
    expect(store.clears, 1);
    controller.dispose();
    await api.dispose();
  });
}
