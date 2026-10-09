import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';

/// Na janela da nuvem, fechar comanda volta para a loja se ela está no ar —
/// igual ao PDV desktop. Cobrar o mesmo cartão nos dois servidores é dinheiro
/// em dobro (simulação do dia a dia).
void main() {
  test('recusa cobrar_na_loja manda o fechamento para a loja', () async {
    var lojaFora = true;
    final naLoja = <String>[];
    final api = ApiClient(
      baseUrlProvider: () => 'http://loja.local/api/v1',
      httpClient: MockClient((request) async {
        if (request.url.host == 'loja.local') {
          if (lojaFora) throw const SocketException('fora');
          naLoja.add(request.url.path);
          return http.Response('{"id": "pedido-1", "total": "10.00"}', 200);
        }
        if (request.url.path.endsWith('/attach-commands/')) {
          return http.Response(
            '{"success": false, "error": {"code": "cobrar_na_loja", '
            '"message": "A loja está no ar"}}',
            409,
          );
        }
        return http.Response('{"id": "x"}', 200);
      }),
    );

    await api.request('GET', '/orders/');
    lojaFora = false;
    final pedido = await api.request(
      'POST',
      '/orders/pedido-1/attach-commands/',
      body: {
        'commands': ['c1'],
      },
      idempotencyKey: 'k1',
    );

    expect(pedido['total'], '10.00');
    expect(naLoja, ['/api/v1/orders/pedido-1/attach-commands/']);
  });
}
