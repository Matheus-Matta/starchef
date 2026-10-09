import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';

/// O pedido aberto na nuvem com a loja fora não "some" quando o app volta
/// para a loja antes de a sincronização descê-lo — igual ao PDV desktop.
///
/// Achado pela simulação do dia a dia (`loadtest/dia_a_dia`): o recebimento
/// levava "404 pedido não encontrado" e a conta ficava aberta.
void main() {
  test('404 da loja num pedido que nasceu na nuvem vai para a nuvem', () async {
    var lojaFora = true;
    final naNuvem = <String>[];
    final api = ApiClient(
      baseUrlProvider: () => 'http://loja.local/api/v1',
      httpClient: MockClient((request) async {
        if (request.url.host == 'loja.local') {
          if (lojaFora) throw const SocketException('conexão recusada');
          if (request.url.path.endsWith('/health/')) {
            return http.Response('{}', 200);
          }
          return http.Response('{"detail": "No Order matches."}', 404);
        }
        naNuvem.add('${request.method} ${request.url.path}');
        if (request.url.path.endsWith('/orders/')) {
          return http.Response('{"id": "pedido-da-nuvem"}', 201);
        }
        return http.Response(
          '{"id": "pedido-da-nuvem", "status": "paid"}',
          200,
        );
      }),
    );

    await api.request('POST', '/orders/', body: {'order_type': 'command'});
    lojaFora = false;
    api.cloudFallback.localRespondeu();

    final pago = await api.request(
      'POST',
      '/orders/pedido-da-nuvem/pay/',
      body: {'amount': '10.00'},
      idempotencyKey: 'rec-1',
    );

    expect(pago['status'], 'paid');
    expect(naNuvem.last, 'POST /api/v1/orders/pedido-da-nuvem/pay/');
  });
}
