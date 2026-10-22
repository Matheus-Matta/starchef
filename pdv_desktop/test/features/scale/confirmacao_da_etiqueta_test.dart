import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_desktop/features/scale/data/etiqueta_da_pesagem.dart';

/// A etiqueta saiu no papel; a confirmação ao servidor INSISTE.
///
/// Com o servidor lento, o `mark-printed` falhava uma vez e a estação
/// desistia: a reserva vencia, o trabalho voltava à fila e um PDV imprimia de
/// novo — "a comanda 7 saiu umas 5 vezes seguidas".
void main() {
  test('confirmação que falha é tentada de novo até chegar', () async {
    var marcas = 0;
    final api = ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      cloudFallback: CloudFallback(enabled: false),
      client: MockClient((request) async {
        if (request.url.path.endsWith('/mark-printed/') && ++marcas < 3) {
          return http.Response('{"detail": "indisponível"}', 503);
        }
        return http.Response(
          jsonEncode({'id': 'job-1'}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    addTearDown(api.dispose);
    final esperas = <Duration>[];
    final etiqueta = EtiquetaDaPesagem(
      api,
      accessToken: 't',
      enviar: (_, _) async {},
      esperar: (pausa) async => esperas.add(pausa),
    );

    await etiqueta.imprimir(
      job: const {
        'id': 'job-1',
        'printer': 'imp-1',
        'payload': {'text_content': 'COMANDA 7'},
      },
      impressora: const {
        'id': 'imp-1',
        'name': 'Balança',
        'connection_type': 'serial',
        'endpoint': 'COM3',
      },
    );
    await etiqueta.confirmando;

    expect(marcas, 3);
    expect(esperas, hasLength(2));
  });
}
