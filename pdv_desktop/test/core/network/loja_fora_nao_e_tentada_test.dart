import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';

/// Confirmada a queda, a próxima requisição não bate na loja.
///
/// Cada gesto tentava a loja primeiro, mesmo dentro da janela: a que acertava
/// mostrava "loja", a seguinte "nuvem", e o mesmo pedido era editado nos dois
/// servidores com segundos de diferença.
void main() {
  test('dentro da janela a requisicao vai direto a nuvem', () async {
    var naLoja = 0;
    var naNuvem = 0;
    final api = ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((request) async {
        if (request.url.host == 'loja.local') {
          naLoja++;
          throw const SocketException('conexão recusada');
        }
        naNuvem++;
        return http.Response('{"results": []}', 200);
      }),
    );

    await api.get('/orders/', accessToken: 'x.eyJ1c2VyX2lkIjoidTEifQ.y');
    final tentativasNaLojaNaQueda = naLoja;
    await api.get('/commands/', accessToken: 'x.eyJ1c2VyX2lkIjoidTEifQ.y');

    expect(
      naLoja,
      tentativasNaLojaNaQueda,
      reason: 'a loja já estava dada como fora',
    );
    expect(naNuvem, 2);
    expect(api.lastServerOrigin, ServerOrigin.nuvem);
    await api.dispose();
  });
}
