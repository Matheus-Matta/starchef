import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';

/// A escrita cuja resposta se perdeu é repetida com a MESMA chave.
///
/// Tempo esgotado numa escrita é o caso em que o servidor pode ter gravado. O
/// erro ia para o operador, que repetia o gesto com chave NOVA — e o item saía
/// duas vezes na comanda (simulação do dia a dia, `loadtest/dia_a_dia`).
void main() {
  const token = 'x.eyJ1c2VyX2lkIjoidTEifQ.y';

  test(
    'tempo esgotado numa escrita repete uma vez com a mesma chave',
    () async {
      final chaves = <String?>[];
      final api = ApiClient(
        baseUrl: 'http://loja.local/api/v1',
        client: MockClient((request) async {
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

      final resposta = await api.post(
        '/commands/c1/items/',
        body: {'product': 'p'},
        accessToken: token,
      );

      expect(resposta['id'], 'item-1');
      expect(chaves, hasLength(2));
      expect(
        chaves.toSet(),
        hasLength(1),
        reason: 'a repetição leva a MESMA chave',
      );
      await api.dispose();
    },
  );

  test('leitura e recusa do servidor nao sao repetidas', () async {
    var chamadas = 0;
    final api = ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((request) async {
        if (request.url.path.endsWith('/health/')) {
          return http.Response('{}', 200);
        }
        chamadas++;
        return http.Response('{"detail": "não"}', 409);
      }),
    );

    await expectLater(
      api.post('/commands/c1/items/', body: const {}, accessToken: token),
      throwsA(isA<Object>()),
    );
    expect(chamadas, 1);
    await api.dispose();
  });
}
