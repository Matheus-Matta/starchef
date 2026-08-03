import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';

/// Token com uma claim de conta, para o escopo da fila ficar estável.
const _token =
    'eyJhbGciOiJIUzI1NiJ9.'
    'eyJhY2NvdW50X2lkIjoiYWNjLTEifQ.'
    'assinatura-irrelevante-no-teste';

void main() {
  late Directory directory;
  var counter = 0;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-orders');
  });

  tearDown(() async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  ApiClient clientWith(http.Client transport) {
    counter += 1;
    return ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: transport,
      offlineStore: OfflineStore(
        file: File(
          '${directory.path}${Platform.pathSeparator}orders-$counter.sqlite',
        ),
      ),
    );
  }

  http.Response json(Object body, [int status = 200]) => http.Response(
    jsonEncode(body),
    status,
    headers: {'content-type': 'application/json'},
  );

  group('leitura de pedidos offline', () {
    test('a lista e o detalhe voltam do cache quando a rede cai', () async {
      var online = true;
      final api = clientWith(
        MockClient((request) async {
          if (!online) throw const SocketException('sem rota');
          if (request.url.path.endsWith('/orders/')) {
            return json({
              'results': [
                {'id': 'order-1', 'sequence': 42},
              ],
            });
          }
          return json({'id': 'order-1', 'sequence': 42, 'items': []});
        }),
      );
      addTearDown(api.dispose);

      await api.get('/orders/', accessToken: _token);
      await api.get('/orders/order-1/', accessToken: _token);

      online = false;
      final list = await api.get('/orders/', accessToken: _token);
      final detail = await api.get('/orders/order-1/', accessToken: _token);

      // Sem isso a tela de Pedidos ficava vazia e não havia como retomar um
      // atendimento já lançado.
      expect(list['_offline_cache'], isTrue);
      expect((list['results'] as List).single['id'], 'order-1');
      expect(detail['_offline_cache'], isTrue);
      expect(detail['sequence'], 42);
    });

    test('o cache é por query: mudar o page_size perde a cópia', () async {
      var online = true;
      final api = clientWith(
        MockClient((request) async {
          if (!online) throw const SocketException('sem rota');
          return json({
            'results': [
              {'id': 'order-1', 'items': []},
            ],
          });
        }),
      );
      addTearDown(api.dispose);

      await api.get(
        '/orders/',
        query: {'page_size': 50, 'ordering': '-opened_at'},
        accessToken: _token,
      );
      online = false;

      final mesmaQuery = await api.get(
        '/orders/',
        query: {'page_size': 50, 'ordering': '-opened_at'},
        accessToken: _token,
      );
      expect(mesmaQuery['_offline_cache'], isTrue);

      // Por isso o aquecimento do cache e a tela de Pedidos precisam usar
      // exatamente a mesma query: um `page_size` diferente é outra entrada e
      // o operador ficaria sem os pedidos offline.
      await expectLater(
        () => api.get(
          '/orders/',
          query: {'page_size': 300, 'ordering': '-opened_at'},
          accessToken: _token,
        ),
        throwsA(isA<ApiException>()),
      );
    });

    test('os pagamentos do pedido também são lidos do cache', () async {
      var online = true;
      final api = clientWith(
        MockClient((request) async {
          if (!online) throw const SocketException('sem rota');
          return json({
            'results': [
              {'id': 'pay-1', 'amount': '25.00'},
            ],
          });
        }),
      );
      addTearDown(api.dispose);

      await api.get('/orders/order-1/payments/', accessToken: _token);
      online = false;
      final cached = await api.get(
        '/orders/order-1/payments/',
        accessToken: _token,
      );

      expect(cached['_offline_cache'], isTrue);
    });
  });

  group('fechamento e pagamento offline', () {
    test('fechar, enviar à cozinha e pagar entram na fila', () async {
      final api = clientWith(
        MockClient((_) async => throw const SocketException('sem rota')),
      );
      addTearDown(api.dispose);

      for (final path in [
        '/orders/order-1/close/',
        '/orders/order-1/send-to-kitchen/',
        '/orders/order-1/pay/',
      ]) {
        final queued = await api.post(
          path,
          body: const {'amount': '10.00'},
          accessToken: _token,
        );
        expect(
          queued['_offline_pending'],
          isTrue,
          reason: '$path deveria ficar na fila em vez de falhar',
        );
      }

      expect(await api.pendingOperations(), 3);
    });

    test('cada operação da fila leva sua própria chave', () async {
      final api = clientWith(
        MockClient((_) async => throw const SocketException('sem rota')),
      );
      addTearDown(api.dispose);

      await api.post(
        '/orders/order-1/pay/',
        body: const {'amount': '10.00'},
        accessToken: _token,
      );
      await api.post(
        '/orders/order-1/pay/',
        body: const {'amount': '20.00'},
        accessToken: _token,
      );

      final operations = await api.outboxOperations();
      final keys = operations
          .map((item) => '${item['idempotency_key']}')
          .toSet();
      // Chaves distintas: são dois pagamentos reais, não um reenvio.
      expect(keys, hasLength(2));
    });

    test('o pagamento enfileirado devolve o valor para a tela somar', () async {
      final api = clientWith(
        MockClient((_) async => throw const SocketException('sem rota')),
      );
      addTearDown(api.dispose);

      final queued = await api.post(
        '/orders/order-1/pay/',
        body: const {'payment_method': 'pm-1', 'amount': '25.00'},
        accessToken: _token,
      );

      // A tela soma os pagamentos para saber quanto falta. Sem o valor de
      // volta, o restante nunca zeraria e o operador não fecharia a venda.
      expect(queued['_offline_pending'], isTrue);
      expect(queued['amount'], '25.00');
      expect(queued['payment_method'], 'pm-1');
    });

    test('a impressão continua exigindo servidor', () async {
      final api = clientWith(
        MockClient((_) async => throw const SocketException('sem rota')),
      );
      addTearDown(api.dispose);

      // Um cupom não pode "sair da fila" mais tarde: ou imprime agora, ou o
      // operador precisa saber que não saiu.
      await expectLater(
        () => api.post(
          '/orders/order-1/print/',
          body: const {},
          accessToken: _token,
        ),
        throwsA(isA<ApiException>()),
      );
      expect(await api.pendingOperations(), 0);
    });
  });

  test('falha de rede é marcada como conectividade', () async {
    final api = clientWith(
      MockClient((_) async => throw const SocketException('sem rota')),
    );
    addTearDown(api.dispose);

    try {
      await api.post(
        '/orders/order-1/print/',
        body: const {},
        accessToken: _token,
      );
      fail('deveria ter lançado');
    } on ApiException catch (error) {
      // A interface usa esse sinal para mostrar um aviso só, em vez de um
      // alerta por chamada.
      expect(error.isConnectivity, isTrue);
      expect(error.statusCode, isNull);
    }
  });
}
