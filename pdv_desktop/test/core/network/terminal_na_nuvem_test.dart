import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';

/// Desviada para a nuvem, a requisição continua dizendo DE QUAL terminal veio.
///
/// O desvio mandava só o token. Para a nuvem o pagamento chegava "sem
/// terminal": o servidor imprimia o recibo sozinho (ignorando a loja que o
/// desligou) e a regra de dono da sessão de caixa não reconhecia a máquina.
void main() {
  test('a requisição desviada leva X-Terminal-Id e X-Terminal-Name', () async {
    final daNuvem = <http.BaseRequest>[];
    final api =
        ApiClient(
            baseUrl: 'http://loja.local/api/v1',
            client: MockClient((request) async {
              if (request.url.host == 'loja.local') {
                throw const SocketException('conexão recusada');
              }
              daNuvem.add(request);
              return http.Response('{"results": []}', 200);
            }),
          )
          ..installationId = 'inst-123'
          ..terminalLabel = 'Balcão 01';

    await api.get('/orders/', accessToken: 'x.eyJ1c2VyX2lkIjoidTEifQ.y');

    expect(daNuvem, hasLength(1));
    expect(daNuvem.single.headers['X-Terminal-Id'], 'inst-123');
    // Acentuado vai percent-encoded, igual ao caminho da loja.
    expect(daNuvem.single.headers['X-Terminal-Name'], 'Balc%C3%A3o%2001');
    await api.dispose();
  });
}
