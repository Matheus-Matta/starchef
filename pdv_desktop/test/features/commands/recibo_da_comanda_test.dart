import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_repository.dart';

/// O recibo da comanda vai para a impressora MASTER do terminal e é impresso
/// aqui. Antes ia sem impressora nenhuma para a fila do servidor, que escolhia
/// a primeira por nome — e o papel não saía.
void main() {
  test(
    'pede o recibo na impressora escolhida, para o terminal imprimir',
    () async {
      Map<String, dynamic>? corpo;
      final api = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        client: MockClient((request) async {
          corpo = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'print_job_id': 'j1',
              'printer': {'id': 'p-master'},
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }),
      );
      final repositorio = CommandRepository(api, accessToken: 't');

      final job = await repositorio.receipt(
        'c1',
        printerId: 'p-master',
        manualOnly: true,
      );

      expect(corpo, {'printer': 'p-master', 'manual_only': true});
      expect((job['printer'] as Map)['id'], 'p-master');
      await api.dispose();
    },
  );

  test('sem impressora escolhida o servidor decide (a de caixa)', () async {
    Map<String, dynamic>? corpo;
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient((request) async {
        corpo = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          '{}',
          201,
          headers: {'content-type': 'application/json'},
        );
      }),
    );

    await CommandRepository(api, accessToken: 't').receipt('c1');

    expect(corpo, {'manual_only': false});
    await api.dispose();
  });
}
