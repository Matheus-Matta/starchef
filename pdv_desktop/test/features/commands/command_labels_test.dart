import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_listing.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_repository.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/command_labels.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/print_document.dart';

/// As regras das etiquetas e a lista de comandas que vai até o fim.
void main() {
  group('trabalho da etiqueta', () {
    test('leva o número no texto e o código no QR e nas barras', () {
      final documento = PrintDocument.fromRemoteJob(
        trabalhoDeEtiqueta({'number': 12, 'code': 'CMD-0012'}),
      );

      expect(documento.type, PrintJobType.commandLabel);
      expect(documento.content, '12');
      expect(documento.barcode, 'CMD-0012');
      expect(documento.qr, 'CMD-0012');
    });

    test('comanda sem código usa o número, como o recibo', () {
      final documento = PrintDocument.fromRemoteJob(
        trabalhoDeEtiqueta({'number': 7, 'code': ''}),
      );

      expect(documento.barcode, '7');
      expect(documento.qr, '7');
    });
  });

  group('faixa', () {
    String ultimoErro = '';
    ({int de, int ate})? faixa(String de, String ate) =>
        faixaValida(de, ate, (m) => ultimoErro = m);

    test('aceita de 10 a 100', () {
      expect(faixa('10', '100'), (de: 10, ate: 100));
      expect(faixa(' 5 ', '5'), (de: 5, ate: 5));
    });

    test('recusa vazio, letra, zero, invertida e grande demais', () {
      expect(faixa('', '10'), isNull);
      expect(faixa('a', '10'), isNull);
      expect(faixa('0', '10'), isNull);
      expect(faixa('100', '10'), isNull);
      expect(ultimoErro, contains('maior que o final'));
      expect(faixa('1', '1001'), isNull);
      expect(ultimoErro, contains('1000'));
    });
  });

  test('números sem cadastro e a lista curta', () {
    final faltam = numerosSemCadastro(10, 15, [
      {'number': 10},
      {'number': '12'},
      {'number': 15},
    ]);

    expect(faltam, [11, 13, 14]);
    expect(listaCurta([1, 2, 3]), '1, 2, 3');
    expect(
      listaCurta(List.generate(12, (i) => i + 1)),
      '1, 2, 3, 4, 5, 6, 7, 8 e mais 4',
    );
  });

  group('lista de comandas', () {
    late List<Uri> pedidos;
    late ApiClient api;

    CommandRepository repositorio(http.Response Function(Uri) servidor) {
      pedidos = [];
      api = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        client: MockClient((request) async {
          pedidos.add(request.url);
          return servidor(request.url);
        }),
      );
      return CommandRepository(api, accessToken: 'x');
    }

    http.Response pagina(List<int> numeros, {bool proxima = false}) =>
        http.Response(
          jsonEncode({
            'results': [
              for (final n in numeros) {'id': 'c$n', 'number': n},
            ],
            'next': proxima
                ? 'http://starchef.test/api/v1/commands/?page=2'
                : null,
          }),
          200,
        );

    test('passa das 100 primeiras: segue as páginas até o fim', () async {
      repositorio(
        (url) => url.queryParameters['page'] == '1'
            ? pagina(List.generate(100, (i) => i + 1), proxima: true)
            : pagina([101, 102]),
      );

      final todas = await listarComandas(api, restaurantId: 'r1');

      expect(todas, hasLength(102));
      expect(pedidos.map((u) => u.queryParameters['page']), ['1', '2']);
      expect(pedidos.first.queryParameters['page_size'], '100');
    });

    test('a faixa vai para o servidor', () async {
      final repo = repositorio((_) => pagina([10, 11]));

      await repo.inRange(de: 10, ate: 100, restaurantId: 'r1');

      expect(pedidos.single.queryParameters, containsPair('number_min', '10'));
      expect(pedidos.single.queryParameters, containsPair('number_max', '100'));
      expect(pedidos.single.queryParameters, containsPair('restaurant', 'r1'));
    });

    test('resposta em formato desconhecido é erro, não lista vazia', () async {
      repositorio((_) => http.Response('{"results": "nada"}', 200));

      await expectLater(listarComandas(api), throwsA(isA<ApiException>()));
    });
  });
}
