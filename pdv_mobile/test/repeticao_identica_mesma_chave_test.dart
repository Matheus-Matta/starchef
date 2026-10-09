import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';

/// O garçom repete o MESMO lançamento depois da rede falhar: mesma chave —
/// igual ao PDV desktop. Sem isto o item saía em dobro na comanda.
void main() {
  test(
    'repetição idêntica depois de falha de rede leva a mesma chave',
    () async {
      final chaves = <String?>[];
      var falhar = true;
      final api = ApiClient(
        baseUrlProvider: () => 'http://loja.local/api/v1',
        httpClient: MockClient((request) async {
          if (request.url.host != 'loja.local' ||
              request.url.path.endsWith('/health/')) {
            throw const SocketException('fora');
          }
          chaves.add(request.headers['Idempotency-Key']);
          if (falhar) throw const SocketException('a rede caiu');
          return http.Response('{"id": "item-1"}', 201);
        }),
      );
      const corpo = {'product': 'p1', 'quantity': 1};

      await expectLater(
        api.request(
          'POST',
          '/commands/c1/items/',
          body: corpo,
          idempotencyKey: 'gesto-1',
        ),
        throwsA(isA<Object>()),
      );
      falhar = false;
      await api.request(
        'POST',
        '/commands/c1/items/',
        body: corpo,
        idempotencyKey: 'gesto-2',
      );
      await api.request(
        'POST',
        '/commands/c1/items/',
        body: corpo,
        idempotencyKey: 'gesto-3',
      );

      expect(chaves.first, 'gesto-1');
      expect(
        chaves[chaves.length - 2],
        'gesto-1',
        reason: 'a repetição é a mesma operação',
      );
      expect(
        chaves.last,
        'gesto-3',
        reason: 'depois do sucesso é um gesto novo',
      );
    },
  );
}
