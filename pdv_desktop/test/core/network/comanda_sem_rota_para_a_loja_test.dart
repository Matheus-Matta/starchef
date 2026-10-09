import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';

/// Só a ida pela janela do veredito pede para a nuvem conferir a loja.
///
/// A v3.0.86 recusava na nuvem todo fechamento de comanda com a loja dando
/// sinal de vida — inclusive do terminal configurado direto na nuvem ou sem
/// rota até a loja, e a comanda não fechava em lugar nenhum. Agora o PDV marca
/// (`X-Desvio-Da-Loja: janela`) só o pedido que foi direto, sem tentar a loja.
void main() {
  const token = 'x.eyJ1c2VyX2lkIjoidTEifQ.y';

  test(
    'loja sem rota: o fechamento vai à nuvem sem a marca da janela',
    () async {
      final marcas = <String?>[];
      final api = ApiClient(
        baseUrl: 'http://loja.local/api/v1',
        client: MockClient((request) async {
          if (request.url.host == 'loja.local') {
            throw const SocketException('sem rota');
          }
          marcas.add(request.headers['X-Desvio-Da-Loja']);
          return http.Response('{"id": "pedido-1", "total": "10.00"}', 200);
        }),
      );

      final pedido = await api.post(
        '/orders/pedido-1/attach-commands/',
        body: {
          'commands': ['c1'],
        },
        accessToken: token,
      );

      expect(pedido['total'], '10.00');
      expect(marcas, [null]);
      await api.dispose();
    },
  );

  test('na janela, o que vai direto à nuvem leva a marca', () async {
    final marcas = <String, String?>{};
    final api = ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((request) async {
        if (request.url.host == 'loja.local') {
          throw const SocketException('fora');
        }
        marcas[request.url.path] = request.headers['X-Desvio-Da-Loja'];
        return http.Response('{"id": "pedido-1"}', 200);
      }),
    );

    await api.get('/orders/', accessToken: token); // abre a janela da nuvem
    await api.post(
      '/orders/pedido-1/detach-commands/',
      body: {},
      accessToken: token,
    );

    expect(marcas['/api/v1/orders/pedido-1/detach-commands/'], 'janela');
    await api.dispose();
  });
}
