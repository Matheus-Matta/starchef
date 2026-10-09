import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';

/// O operador repete o MESMO lançamento depois da rede falhar: mesma chave.
///
/// Sem isto, a repetição saía com chave nova e, quando a rede voltava, o
/// servidor gravava as duas — o item em dobro na comanda (simulação do dia a
/// dia, `loadtest/dia_a_dia`).
void main() {
  const token = 'x.eyJ1c2VyX2lkIjoidTEifQ.y';
  const corpo = {'product': 'p1', 'quantity': 1};

  test(
    'repetição idêntica depois de falha de rede leva a mesma chave',
    () async {
      final chaves = <String?>[];
      var falhar = true;
      final api = ApiClient(
        baseUrl: 'http://loja.local/api/v1',
        cloudFallback: CloudFallback(enabled: false),
        client: MockClient((request) async {
          if (request.url.path.endsWith('/health/')) {
            throw const SocketException('fora');
          }
          chaves.add(request.headers['Idempotency-Key']);
          if (falhar) throw const SocketException('a rede caiu');
          return http.Response('{"id": "item-1"}', 201);
        }),
      );

      await expectLater(
        api.post('/commands/c1/items/', body: corpo, accessToken: token),
        throwsA(isA<Object>()),
      );
      falhar = false;
      await api.post('/commands/c1/items/', body: corpo, accessToken: token);
      await api.post('/commands/c1/items/', body: corpo, accessToken: token);

      expect(chaves[0], chaves[1], reason: 'a repetição é a mesma operação');
      expect(
        chaves[2],
        isNot(chaves[1]),
        reason: 'depois do sucesso é um gesto novo',
      );
      await api.dispose();
    },
  );
}
