import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_desktop/features/home/data/nota_do_pedido.dart';

/// O `/invoices/emit/` falhou ou demorou, mas a nota pode existir.
///
/// Achado na loja: com a SEFAZ lenta, o pedido do PDV esbarrava na emissão
/// automática e voltava "Pedido já possui nota fiscal emitida" — e o PDV
/// desistia do DANFE de uma nota que existia. Agora ele procura a nota pelo
/// pedido antes de desistir.
void main() {
  const token = 'x.eyJ1c2VyX2lkIjoidTEifQ.y';
  const semEspera = [Duration.zero, Duration.zero, Duration.zero];

  ApiClient apiQueResponde(List<Map<String, dynamic>> pedidos) {
    var chamada = 0;
    return ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      cloudFallback: CloudFallback(enabled: false),
      client: MockClient((request) async {
        final pedido = pedidos[chamada.clamp(0, pedidos.length - 1)];
        chamada++;
        return http.Response(jsonEncode(pedido), 200);
      }),
    );
  }

  test('acha a nota quando ela aparece no pedido', () async {
    final api = apiQueResponde([
      {'id': 'p1', 'fiscal': null},
      {
        'id': 'p1',
        'fiscal': {
          'id': 'n1',
          'fiscal_state': 'authorized',
          'printable': true,
          'number': '42',
        },
      },
    ]);

    final nota = await NotaDoPedido(
      api,
      accessToken: token,
      esperas: semEspera,
    ).esperar('p1');

    expect(nota?['id'], 'n1');
    expect(nota?['printable'], isTrue);
    await api.dispose();
  });

  test(
    'sem nota na janela, devolve nulo em vez de esperar para sempre',
    () async {
      final api = apiQueResponde([
        {'id': 'p1', 'fiscal': null},
      ]);

      final nota = await NotaDoPedido(
        api,
        accessToken: token,
        esperas: semEspera,
      ).esperar('p1');

      expect(nota, isNull);
      await api.dispose();
    },
  );
}
