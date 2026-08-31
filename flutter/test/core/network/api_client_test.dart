import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';
import 'package:starchef_pdv/core/network/realtime_client.dart';

void main() {
  test('troca a API em memória sem reiniciar o aplicativo', () async {
    final directory = await Directory.systemTemp.createTemp(
      'starchef-api-switch-',
    );
    final client = ApiClient(
      baseUrl: 'https://old.starchef.test/api/v1',
      offlineStore: OfflineStore(
        file: File('${directory.path}/offline.sqlite'),
      ),
    );

    await client.updateBaseUrl('https://api.starchef.com.br/api/v1');

    expect(client.baseUrl, 'https://api.starchef.com.br/api/v1');
    expect(client.healthEndpoint, 'https://api.starchef.com.br/health/');
    expect(
      client.pdvSocketUrl('restaurant-1'),
      'wss://api.starchef.com.br/ws/pdv/restaurant-1/',
    );
    await client.dispose();
    await directory.delete(recursive: true);
  });

  test('evento WS da unidade vira atualização local em tempo real', () async {
    final client = ApiClient(baseUrl: 'http://starchef.test/api/v1');
    final received = <String>[];
    final subscription = client.signals.changes.listen(received.add);

    client.applyRealtimeEvent(
      const RealtimeEvent('model.updated', {
        'resource': 'orders.orderitem',
        'restaurant_id': 'restaurant-1',
      }),
      restaurantId: 'restaurant-1',
    );
    client.applyRealtimeEvent(
      const RealtimeEvent('model.updated', {
        'resource': 'menu.product',
        'restaurant_id': 'restaurant-2',
      }),
      restaurantId: 'restaurant-1',
    );
    await Future<void>.delayed(const Duration(milliseconds: 200));

    expect(received, containsAll({'realtime:orders', 'orders'}));
    expect(received, isNot(contains('realtime:menu')));

    await subscription.cancel();
    await client.dispose();
  });

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
    'persiste formas de pagamento por restaurante para uso offline',
    () async {
      final directory = await Directory.systemTemp.createTemp(
        'starchef-payment-methods-cache-',
      );
      var online = true;
      final client = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        offlineStore: OfflineStore(
          file: File('${directory.path}/offline.sqlite'),
        ),
        client: MockClient((request) async {
          if (!online) throw const SocketException('offline');
          expect(request.url.path, endsWith('/payments/methods/'));
          return http.Response(
            '{"results":[{"id":"pix-1","name":"PIX","method_type":"pix"}]}',
            200,
          );
        }),
      );
      const query = {
        'restaurant': 'restaurant-1',
        'is_active': true,
        'page_size': 100,
      };

      await client.get(
        '/payments/methods/',
        query: query,
        accessToken: 'token',
      );
      online = false;
      final cached = await client.get(
        '/payments/methods/',
        query: query,
        accessToken: 'token',
      );

      expect(cached['_offline_cache'], isTrue);
      expect((cached['results'] as List).single['name'], 'PIX');
      await client.dispose();
      await directory.delete(recursive: true);
    },
  );

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

  // O status da resposta precisa ser lido ANTES do corpo. Decodificar primeiro
  // fazia uma página HTML de erro — 502 do proxy, 500 do Django — estourar
  // `FormatException` e virar um `ApiException` sem `statusCode`. A fila trata
  // isso como recusa de negócio e tira a operação de rotação para sempre: uma
  // oscilação de gateway matava permanentemente um fechamento de caixa
  // enfileirado, e nada no servidor ficava pendente de aprovação.
  test('erro 502 em HTML é indisponibilidade, não recusa definitiva', () async {
    final client = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient(
        (_) async => http.Response(
          '<html><head><title>502 Bad Gateway</title></head>'
          '<body><h1>502 Bad Gateway</h1></body></html>',
          502,
          headers: {'content-type': 'text/html'},
        ),
      ),
    );

    // `isConnectivity` é o que a fila lê: o transporte o converte em
    // `TransientSyncFailure` (reagenda) em vez de recusa definitiva.
    await expectLater(
      client.post('/cash-register/abc/close/', body: const {}),
      throwsA(
        isA<ApiException>()
            .having((error) => error.isConnectivity, 'isConnectivity', isTrue)
            .having((error) => error.message, 'message', contains('502')),
      ),
    );

    await client.dispose();
  });

  test('erro 4xx sem JSON preserva o status e um trecho do corpo', () async {
    final client = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient(
        (_) async => http.Response(
          '<html><body>Request Entity Too Large</body></html>',
          413,
          headers: {'content-type': 'text/html'},
        ),
      ),
    );

    await expectLater(
      client.post('/cash-register/abc/close/', body: const {}),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'statusCode', 413)
            .having(
              (error) => error.message,
              'message',
              contains('Request Entity Too Large'),
            ),
      ),
    );

    await client.dispose();
  });

  test('corpo escalar num erro não derruba a chamada por outro motivo', () async {
    // `raw as Map<String, dynamic>` estourava `TypeError` num corpo assim.
    final client = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient(
        (_) async => http.Response(
          '"falha"',
          400,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );

    await expectLater(
      client.post('/cash-register/abc/close/', body: const {}),
      throwsA(
        isA<ApiException>().having((error) => error.statusCode, 'statusCode', 400),
      ),
    );

    await client.dispose();
  });

  test('sucesso com corpo não-JSON continua sendo resposta inválida', () async {
    final client = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient(
        (_) async => http.Response(
          '<html>ok</html>',
          200,
          headers: {'content-type': 'text/html'},
        ),
      ),
    );

    await expectLater(
      client.post('/cash-register/abc/close/', body: const {}),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'message',
          contains('resposta inválida'),
        ),
      ),
    );

    await client.dispose();
  });

}
