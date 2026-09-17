import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/core/network/realtime_client.dart';

/// O cliente HTTP é o único caminho de dados deste PDV.
///
/// Não há fila de saída nem cache de leitura: o que o servidor responde é o
/// que existe, e o que ele recusa não aconteceu. O que estes testes protegem é
/// a fronteira — que a requisição saia montada certo, e que toda resposta
/// estranha vire uma mensagem que o operador consiga ler.
void main() {
  ApiClient clientWith(
    Future<http.Response> Function(http.Request request) handler,
  ) => ApiClient(
    baseUrl: 'http://starchef.test/api/v1',
    client: MockClient(handler),
  );

  test('nome de terminal acentuado não quebra a requisição', () async {
    // O cabeçalho HTTP só aceita ASCII: `dart:io` recusa qualquer byte acima
    // de 127 com `FormatException`. Bastava a loja batizar o terminal de
    // "Balcão 01" para o aplicativo parar de falar com a API até ser
    // reiniciado — e a mensagem acusava o endereço do servidor por um problema
    // que era inteiramente nosso.
    late http.BaseRequest sent;
    final client = clientWith((request) async {
      sent = request;
      return http.Response('{"ok": true}', 200);
    })
      ..installationId = 'instalacao-2'
      ..terminalLabel = 'Balcão 01';

    await client.post(
      '/cash-register/open/',
      body: const {'opening_amount': 0},
      accessToken: 'token',
    );

    final label = sent.headers['X-Terminal-Name']!;
    expect(
      label.codeUnits.every((unit) => unit <= 127),
      isTrue,
      reason: 'o valor precisa atravessar o cliente HTTP real',
    );
    // E o servidor recupera o nome inteiro: nada de acento perdido no caminho.
    expect(Uri.decodeComponent(label), 'Balcão 01');
    expect(sent.headers['X-Terminal-Id'], 'instalacao-2');

    await client.dispose();
  });

  test('nome de terminal em ASCII viaja sem escapes', () async {
    late http.BaseRequest sent;
    final client = clientWith((request) async {
      sent = request;
      return http.Response('{"ok": true}', 200);
    })
      ..installationId = 'instalacao-1'
      ..terminalLabel = 'Caixa 01';

    await client.get('/cash-register/current/', accessToken: 'token');

    expect(sent.headers['X-Terminal-Name'], 'Caixa 01');
    await client.dispose();
  });

  test('toda escrita leva chave de idempotência; leitura não leva', () async {
    // A requisição pode ter chegado ao servidor e a resposta ter se perdido no
    // caminho. Quando o operador repete o gesto, é esta chave que impede a
    // segunda venda.
    final chaves = <String, String?>{};
    final client = clientWith((request) async {
      chaves[request.method] = request.headers['Idempotency-Key'];
      return http.Response('{"ok": true}', 200);
    });

    await client.get('/orders/', accessToken: 'token');
    await client.post('/orders/', body: const {}, accessToken: 'token');

    expect(chaves['GET'], isNull);
    expect(chaves['POST'], isNotNull);
    await client.dispose();
  });

  test('a repetição após 401 reusa a MESMA chave de idempotência', () async {
    // Um token vencido pode ser recusado DEPOIS de a operação ter sido
    // aplicada. Repetir com chave nova criaria exatamente a venda duplicada
    // que a idempotência existe para evitar.
    final chaves = <String>[];
    var primeira = true;
    final client = clientWith((request) async {
      chaves.add(request.headers['Idempotency-Key']!);
      if (primeira) {
        primeira = false;
        return http.Response(
          '{"detail":"Token expirado."}',
          401,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('{"id":"pedido-1"}', 200);
    });
    client.attachTokenRefresher(() async => 'token-novo');

    final result = await client.post(
      '/orders/',
      body: const {},
      accessToken: 'token-velho',
    );

    expect(result['id'], 'pedido-1');
    expect(chaves, hasLength(2));
    expect(chaves.first, chaves.last);
    await client.dispose();
  });

  test('troca a API em memória sem reiniciar o aplicativo', () async {
    final client = ApiClient(baseUrl: 'https://old.starchef.test/api/v1');

    await client.updateBaseUrl('https://api.starchef.com.br/api/v1');

    expect(client.baseUrl, 'https://api.starchef.com.br/api/v1');
    expect(client.healthEndpoint, 'https://api.starchef.com.br/health/');
    expect(
      client.pdvSocketUrl('restaurant-1'),
      'wss://api.starchef.com.br/ws/pdv/restaurant-1/',
    );
    await client.dispose();
  });

  test('evento WS da unidade avisa quem mostra aquele assunto', () async {
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
    // Evento de OUTRA unidade não mexe na tela desta.
    expect(received, isNot(contains('realtime:menu')));

    await subscription.cancel();
    await client.dispose();
  });

  test('converte resposta de erro da API em ApiException', () async {
    final client = clientWith(
      (_) async => http.Response(
        '{"detail":"Credenciais inválidas."}',
        401,
        headers: {'content-type': 'application/json'},
      ),
    );

    await expectLater(
      client.post('/auth/login/', body: const {}),
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
    final client = clientWith(
      (_) async => http.Response(
        '{"success":false,"status_code":401,"error":'
        '{"code":"authentication_failed","message":"Credenciais inválidas."}}',
        401,
        headers: {'content-type': 'application/json; charset=utf-8'},
      ),
    );

    await expectLater(
      client.post('/auth/login/', body: const {}),
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

  test('sem rede a operação falha, e falha dizendo que falhou', () async {
    // Não existe fila que absorva isto. O gesto do operador não aconteceu, e
    // `isConnectivity` é o que faz a tela dizer "nada foi registrado" em vez
    // de acusar uma recusa do servidor que nunca houve.
    final client = clientWith(
      (_) async => throw const SocketException('sem rota'),
    );

    await expectLater(
      client.post('/orders/', body: const {}, accessToken: 'token'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.isConnectivity, 'isConnectivity', isTrue)
            .having((error) => error.statusCode, 'statusCode', isNull),
      ),
    );
    expect(client.status.phase, NetworkPhase.offline);
    await client.dispose();
  });

  test('uma leitura recusada não devolve dado velho', () async {
    // O PDV antigo respondia do cache aqui. Este não tem de onde: um preço de
    // ontem numa tela de venda é pior do que uma tela vazia com um aviso.
    final client = clientWith(
      (_) async => throw const SocketException('sem rota'),
    );

    await expectLater(
      client.get('/products/', accessToken: 'token'),
      throwsA(isA<ApiException>()),
    );
    await client.dispose();
  });

  test('503 é degradado, e o prazo do servidor é preservado', () async {
    final client = clientWith(
      (_) async => http.Response(
        '{"detail":"Maintenance"}',
        503,
        headers: {'retry-after': '30'},
      ),
    );

    await expectLater(
      client.post('/customers/', body: const {}, accessToken: 'token'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'statusCode', 503)
            .having(
              (error) => error.retryAfter,
              'retryAfter',
              const Duration(seconds: 30),
            ),
      ),
    );
    expect(client.status.phase, NetworkPhase.degraded);
    await client.dispose();
  });

  // O status da resposta precisa ser lido ANTES do corpo. Decodificar primeiro
  // fazia uma página HTML de erro — 502 do proxy, 500 do Django — estourar
  // `FormatException` e virar um `ApiException` sem `statusCode`, escondendo a
  // causa real justamente quando ela era o que o operador precisava ver.
  test('erro 502 em HTML preserva o status e a causa', () async {
    final client = clientWith(
      (_) async => http.Response(
        '<html><head><title>502 Bad Gateway</title></head>'
        '<body><h1>502 Bad Gateway</h1></body></html>',
        502,
        headers: {'content-type': 'text/html'},
      ),
    );

    await expectLater(
      client.post('/cash-register/abc/close/', body: const {}),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'statusCode', 502)
            .having((error) => error.message, 'message', contains('502')),
      ),
    );

    await client.dispose();
  });

  test('erro 4xx sem JSON preserva o status e um trecho do corpo', () async {
    final client = clientWith(
      (_) async => http.Response(
        '<html><body>Request Entity Too Large</body></html>',
        413,
        headers: {'content-type': 'text/html'},
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
    // `raw as Map<String, dynamic>` estourava `TypeError` num corpo assim, e a
    // causa real (o 400) sumia.
    final client = clientWith(
      (_) async => http.Response(
        '"falha"',
        400,
        headers: {'content-type': 'application/json'},
      ),
    );

    await expectLater(
      client.post('/cash-register/abc/close/', body: const {}),
      throwsA(
        isA<ApiException>().having(
          (error) => error.statusCode,
          'statusCode',
          400,
        ),
      ),
    );

    await client.dispose();
  });

  test('sucesso com corpo não-JSON continua sendo resposta inválida', () async {
    final client = clientWith(
      (_) async => http.Response(
        '<html>ok</html>',
        200,
        headers: {'content-type': 'text/html'},
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

  test('uma lista no corpo vira {results: [...]}', () async {
    // Rotas que devolvem lista crua existem, e o resto do PDV só sabe ler
    // `results`.
    final client = clientWith((_) async => http.Response('[{"id":"1"}]', 200));

    final response = await client.get('/printers/', accessToken: 'token');

    expect(response['results'], hasLength(1));
    await client.dispose();
  });
}
