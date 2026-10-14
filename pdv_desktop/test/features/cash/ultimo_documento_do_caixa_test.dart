import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/cash/data/ultimo_documento_do_caixa.dart';

/// Reimprimir a última abertura ou o último fechamento DESTA estação.
///
/// É só leitura: acha a sessão e devolve. Quem imprime é a mesma rota dos
/// comprovantes (`print-document`), sem abrir a gaveta e sem tocar no caixa.
void main() {
  late List<Uri> chamadas;

  ApiClient api(List<Map<String, dynamic>> sessoes) {
    chamadas = [];
    return ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((request) async {
        chamadas.add(request.url);
        if (request.method != 'GET') return http.Response('{}', 405);
        return http.Response(
          jsonEncode({'results': sessoes}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
  }

  test(
    'a ultima abertura vem da estacao, pela abertura mais recente',
    () async {
      final busca = UltimoDocumentoDoCaixa(
        api([
          {'id': 's2'},
        ]),
        accessToken: 't',
      );

      final sessao = await busca.ultimaAbertura(estacao: 'st-1');

      expect(sessao?['id'], 's2');
      final query = chamadas.single.queryParameters;
      expect(chamadas.single.path, endsWith('/cash-register/'));
      expect(query['cash_station'], 'st-1');
      expect(query['ordering'], '-opened_at');
      expect(query['page_size'], '1');
      expect(query.containsKey('status'), isFalse);
    },
  );

  test('o ultimo fechamento so olha caixa fechado, pelo fechamento', () async {
    final busca = UltimoDocumentoDoCaixa(
      api([
        {'id': 's1', 'status': 'closed'},
      ]),
      accessToken: 't',
    );

    final sessao = await busca.ultimoFechamento(estacao: 'st-1');

    expect(sessao?['id'], 's1');
    final query = chamadas.single.queryParameters;
    expect(query['status'], 'closed');
    expect(query['ordering'], '-closed_at');
    expect(query['cash_station'], 'st-1');
  });

  test('sem documento devolve null, para a tela avisar', () async {
    final busca = UltimoDocumentoDoCaixa(api(const []), accessToken: 't');

    expect(await busca.ultimoFechamento(estacao: 'st-1'), isNull);
    expect(await busca.ultimaAbertura(estacao: 'st-1'), isNull);
  });

  test('sem estacao nem consulta: nao ha o que reimprimir', () async {
    final busca = UltimoDocumentoDoCaixa(api(const []), accessToken: 't');

    expect(await busca.ultimaAbertura(estacao: ''), isNull);
    expect(chamadas, isEmpty);
  });
}
