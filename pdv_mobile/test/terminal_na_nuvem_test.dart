import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';

/// Desviada para a nuvem, a requisição do app continua dizendo de qual
/// aparelho veio — sem isso, o pagamento chegava lá "sem terminal" e o
/// servidor imprimia o recibo sozinho.
void main() {
  test('a requisição desviada leva X-Terminal-Id', () async {
    final daNuvem = <http.BaseRequest>[];
    final api =
        ApiClient(
          baseUrlProvider: () => 'http://loja.local/api/v1',
          httpClient: MockClient((request) async {
            if (request.url.host == 'loja.local') {
              throw const SocketException('conexão recusada');
            }
            daNuvem.add(request);
            return http.Response('{"results": []}', 200);
          }),
        )..configureSession(
          accessToken: 'token',
          refreshToken: 'refresh',
          terminalId: 'aparelho-7',
        );

    await api.get('/orders/');

    expect(daNuvem, hasLength(1));
    expect(daNuvem.single.headers['X-Terminal-Id'], 'aparelho-7');
    expect(daNuvem.single.headers['X-Terminal-Name'], 'PDV Mobile');
  });
}
