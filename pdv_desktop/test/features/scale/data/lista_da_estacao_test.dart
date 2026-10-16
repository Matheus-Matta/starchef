import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/scale/data/lista_da_estacao.dart';

/// A estação reaberta não espera a rede: mostra a última lista e relê depois.
void main() {
  late List<String> nomes;
  late Completer<void> servidorLento;
  late int chamadas;

  ApiClient api() => ApiClient(
    baseUrl: 'http://loja.local/api/v1',
    client: MockClient((request) async {
      chamadas++;
      await servidorLento.future;
      return http.Response(
        jsonEncode({
          'results': [
            for (final nome in nomes) {'id': nome, 'name': nome},
          ],
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }),
  );

  setUp(() {
    nomes = ['Balança 1'];
    servidorLento = Completer()..complete();
    chamadas = 0;
  });

  for (final rota in ['/scales/', '/restaurants/']) {
    test(
      '$rota: com cache volta na hora e a versão nova chega depois',
      () async {
        final cliente = api();
        final listas = ListaDaEstacao(cliente, accessToken: 't');
        await listas.ler(rota, query: const {'page_size': 100});

        nomes = ['Balança 1', 'Balança 2'];
        servidorLento = Completer();
        final atualizada = Completer<List<Map<String, dynamic>>>();
        final mostrada = await listas
            .ler(
              rota,
              query: const {'page_size': 100},
              aoAtualizar: atualizada.complete,
            )
            // O servidor está travado: só o cache pode responder a tempo.
            .timeout(const Duration(seconds: 1));

        expect(mostrada.map((b) => b['name']), ['Balança 1']);
        servidorLento.complete();
        final nova = await atualizada.future;
        expect(nova.map((b) => b['name']), ['Balança 1', 'Balança 2']);
        expect(chamadas, 2);
      },
    );
  }

  test('sem nada guardado espera o servidor, como antes', () async {
    final listas = ListaDaEstacao(api(), accessToken: 't');

    final lista = await listas.ler('/scales/', query: const {});

    expect(lista.single['name'], 'Balança 1');
    expect(chamadas, 1);
  });
}
