import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/afinidade_com_a_nuvem.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';

/// O pedido aberto na nuvem com a loja fora não "some" quando o terminal volta
/// para a loja antes de a sincronização descê-lo.
///
/// Achado pela simulação do dia a dia (`loadtest/dia_a_dia`): o recebimento
/// levava "404 pedido não encontrado" e a conta ficava aberta.
void main() {
  const token = 'x.eyJ1c2VyX2lkIjoidTEifQ.y';

  test('404 da loja num pedido que nasceu na nuvem vai para a nuvem', () async {
    var lojaFora = true;
    final naNuvem = <String>[];
    final api = ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((request) async {
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

    await api.post(
      '/orders/',
      body: {'order_type': 'command'},
      accessToken: token,
    );
    lojaFora = false;
    api.cloudFallback.localRespondeu();

    final pago = await api.post(
      '/orders/pedido-da-nuvem/pay/',
      body: {'amount': '10.00'},
      accessToken: token,
    );

    expect(pago['status'], 'paid');
    expect(naNuvem.last, 'POST /api/v1/orders/pedido-da-nuvem/pay/');
    await api.dispose();
  });

  test('a lembrança vence depois de 10 minutos', () {
    var agora = DateTime(2026, 10, 8, 12);
    final afinidade = AfinidadeComANuvem(relogio: () => agora)
      ..lembrar({'id': 'p1'});
    expect(afinidade.tocaNaNuvem('/orders/p1/pay/'), isTrue);
    agora = agora.add(const Duration(minutes: 11));
    expect(afinidade.tocaNaNuvem('/orders/p1/pay/'), isFalse);
  });
}
