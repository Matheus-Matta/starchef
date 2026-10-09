import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';

/// Na janela da nuvem, fechar comanda volta para a loja se ela está no ar.
///
/// A nuvem recusa com 409 `cobrar_na_loja`: cobrar o mesmo cartão nos dois
/// servidores é dinheiro em dobro (simulação do dia a dia).
void main() {
  const token = 'x.eyJ1c2VyX2lkIjoidTEifQ.y';

  test('recusa cobrar_na_loja manda o fechamento para a loja', () async {
    var lojaFora = true;
    final naLoja = <String>[];
    final api = ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((request) async {
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

    await api.get(
      '/orders/',
      accessToken: token,
    ); // cai e abre a janela da nuvem
    lojaFora = false;
    final pedido = await api.post(
      '/orders/pedido-1/attach-commands/',
      body: {
        'commands': ['c1'],
      },
      accessToken: token,
    );

    expect(pedido['total'], '10.00');
    expect(naLoja, ['/api/v1/orders/pedido-1/attach-commands/']);
    expect(api.lastServerOrigin, ServerOrigin.loja);
    await api.dispose();
  });
}
