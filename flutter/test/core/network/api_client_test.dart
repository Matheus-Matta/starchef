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
    await client.dispose();
  });

  test('le a mensagem do envelope padrao de erros do DRF', () async {
    final client = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient(
        (_) async => http.Response(
          '{"success":false,"status_code":401,"error":{"code":"authentication_failed","message":"Credenciais inválidas."}}',
          401,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      ),
    );

    expect(
      () => client.post('/auth/login/', body: const {}),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'message',
          'Credenciais inválidas.',
        ),
      ),
    );
    await client.dispose();
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
    await client.dispose();
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
      await client.dispose();
      await directory.delete(recursive: true);
    },
  );

  test(
    'resolve IDs locais entre pedido e item no mesmo ciclo de sincronização',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'starchef-dependent-outbox-',
      );
      var online = false;
      final requestedPaths = <String>[];
      final client = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        offlineStore: OfflineStore(
          file: File('${directory.path}/offline.sqlite'),
        ),
        client: MockClient((request) async {
          if (!online) throw const SocketException('offline');
          requestedPaths.add(request.url.path);
          if (request.url.path.endsWith('/orders/')) {
            return http.Response('{"id":"server-order"}', 201);
          }
          if (request.url.path.endsWith('/orders/server-order/items/')) {
            return http.Response('{"id":"server-item"}', 201);
          }
          return http.Response('{"detail":"path inesperado"}', 404);
        }),
      );

      final order = await client.post(
        '/orders/',
        body: const {'order_type': 'counter'},
        accessToken: 'token',
      );
      final localOrderId = '${order['id']}';
      await client.post(
        '/orders/$localOrderId/items/',
        body: const {'product': 'product-1', 'quantity': 1},
        accessToken: 'token',
      );
      expect(await client.pendingOperations(), 2);

      online = true;
      await client.syncPendingNow();

      expect(await client.pendingOperations(), 0);
      expect(
        requestedPaths,
        containsAllInOrder([
          '/api/v1/orders/',
          '/api/v1/orders/server-order/items/',
        ]),
      );
      expect(requestedPaths.any((path) => path.contains('offline-')), isFalse);
      await client.dispose();
      await directory.delete(recursive: true);
    },
  );

  test('não usa cache nem fila genérica para operações físicas', () async {
    final directory = await Directory.systemTemp.createTemp(
      'starchef-physical-',
    );
    var online = true;
    final client = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      offlineStore: OfflineStore(
        file: File('${directory.path}/offline.sqlite'),
      ),
      client: MockClient((request) async {
        if (!online) throw const SocketException('offline');
        return http.Response(
          '{"id":"reading-1","weight_kg":"0.500","is_stable":true}',
          200,
        );
      }),
    );

    await client.get('/scales/scale-1/latest-reading/', accessToken: 'token');
    online = false;

    await expectLater(
      client.get('/scales/scale-1/latest-reading/', accessToken: 'token'),
      throwsA(isA<ApiException>()),
    );
    await expectLater(
      client.post(
        '/scales/scale-1/checkout-command/',
        body: const {'command_code': '10', 'scale_reading': 'reading-1'},
        accessToken: 'token',
      ),
      throwsA(isA<ApiException>()),
    );
    expect(await client.pendingOperations(), 0);
    await client.dispose();
    await directory.delete(recursive: true);
  });

  test('classifica 503 como degradado e preserva a mutação local', () async {
    final directory = await Directory.systemTemp.createTemp(
      'starchef-degraded-',
    );
    final client = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      offlineStore: OfflineStore(
        file: File('${directory.path}/offline.sqlite'),
      ),
      client: MockClient(
        (_) async => http.Response(
          '{"detail":"Maintenance"}',
          503,
          headers: {'retry-after': '30'},
        ),
      ),
    );

    final queued = await client.post(
      '/customers/',
      body: const {'name': 'Cliente local'},
      accessToken: 'token',
    );

    expect(queued['_offline_pending'], isTrue);
    expect(client.syncStatus.phase, NetworkSyncPhase.degraded);
    expect(client.syncStatus.retrying + client.syncStatus.pending, 1);
    await client.dispose();
    await directory.delete(recursive: true);
  });
}
