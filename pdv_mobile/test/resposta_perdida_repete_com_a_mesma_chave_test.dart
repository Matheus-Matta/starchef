import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';

/// A escrita cuja resposta se perdeu é repetida com a MESMA chave — igual ao
/// PDV desktop. Sem isto o garçom repetia o gesto com chave nova e o item saía
/// duas vezes na comanda (simulação do dia a dia, `loadtest/dia_a_dia`).
void main() {
  test(
    'tempo esgotado numa escrita repete uma vez com a mesma chave',
    () async {
      final chaves = <String?>[];
      final api = ApiClient(
        baseUrlProvider: () => 'http://loja.local/api/v1',
        httpClient: MockClient((request) async {
          if (request.url.path.endsWith('/health/')) {
            return http.Response('{}', 200);
          }
          chaves.add(request.headers['Idempotency-Key']);
          if (chaves.length == 1) {
            throw TimeoutException('a resposta se perdeu');
          }
          return http.Response('{"id": "item-1"}', 201);
        }),
      );

      final resposta = await api.request(
        'POST',
        '/commands/c1/items/',
        body: {'product': 'p'},
        idempotencyKey: 'op-1',
      );

      expect(resposta['id'], 'item-1');
      expect(chaves, ['op-1', 'op-1']);
    },
  );
}
