import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';

void main() {
  test('converte resposta de erro da API em ApiException', () async {
    final client = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient(
        (_) async => http.Response(
          '{"detail":"Credenciais inválidas."}',
          401,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );

    expect(
      () => client.post('/auth/login/', body: const {}),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'statusCode', 401)
            .having(
              (error) => error.message,
              'message',
              'Credenciais inválidas.',
            ),
      ),
    );
  });

  test('usa cache local quando a API fica offline', () async {
    final directory = await Directory.systemTemp.createTemp('starchef-cache-');
    var online = true;
    final client = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      offlineStore: OfflineStore(file: File('${directory.path}/offline.json')),
      client: MockClient((_) async {
        if (!online) throw const SocketException('offline');
        return http.Response('{"results":[{"id":"1","name":"Pizza"}]}', 200);
      }),
    );

    final connected = await client.get('/menu/products/', accessToken: 'token');
    online = false;
    final offline = await client.get('/menu/products/', accessToken: 'token');

    expect(connected['results'], hasLength(1));
    expect(offline['_offline_cache'], isTrue);
    expect((offline['results'] as List).first['name'], 'Pizza');
    client.dispose();
    await directory.delete(recursive: true);
  });

  test(
    'enfileira alteração offline e sincroniza quando a rede volta',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'starchef-outbox-',
      );
      var online = false;
      final client = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        offlineStore: OfflineStore(
          file: File('${directory.path}/offline.json'),
        ),
        client: MockClient((request) async {
          if (!online) throw const SocketException('offline');
          return http.Response(
            '{"id":"server-1","name":"Cliente offline"}',
            201,
          );
        }),
      );

      final queued = await client.post(
        '/customers/',
        body: const {'name': 'Cliente offline'},
        accessToken: 'token',
      );
      expect(queued['_offline_pending'], isTrue);
      expect(await client.pendingOperations(), 1);

      online = true;
      await client.syncPendingNow();
      expect(await client.pendingOperations(), 0);
      client.dispose();
      await directory.delete(recursive: true);
    },
  );
}
