import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/scale/data/lancamento_da_pesagem.dart';

/// Lançar o peso na comanda é UMA ida ao servidor.
///
/// Eram duas em sequência — registrar a leitura e só então lançar —, e a tela
/// girava pelas duas. O lançamento aceita o peso direto e cria a leitura na
/// mesma transação (`checkout-command`).
void main() {
  late List<http.Request> chamadas;

  ApiClient api({Map<String, dynamic>? resposta}) {
    chamadas = [];
    return ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((request) async {
        chamadas.add(request);
        return http.Response(
          jsonEncode(
            resposta ??
                {
                  'print_job': {'id': 'job-1'},
                },
          ),
          201,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
  }

  test('lanca com uma requisicao so, levando o peso', () async {
    final lancamento = LancamentoDaPesagem(api(), accessToken: 't');

    final resultado = await lancamento.lancar(
      balanca: 'bal-1',
      comanda: '42',
      pesoKg: 0.4567,
      extras: const [],
      imprimir: true,
    );

    expect(chamadas, hasLength(1));
    expect(
      chamadas.single.url.path,
      endsWith('/scales/bal-1/checkout-command/'),
    );
    final corpo = jsonDecode(chamadas.single.body) as Map<String, dynamic>;
    expect(corpo['command_code'], '42');
    expect(corpo['weight_kg'], '0.457');
    expect(corpo['tare_kg'], '0.000');
    expect(corpo['print'], isTrue);
    // A etiqueta nasce reservada para esta estação, que a imprime ela mesma.
    expect(corpo['imprime_aqui'], isTrue);
    expect(corpo['id'], isNotEmpty);
    expect(corpo.containsKey('scale_reading'), isFalse);
    expect(resultado.printJob?['id'], 'job-1');
  });

  test(
    'comanda automatica pede ao servidor e devolve o numero usado',
    () async {
      final lancamento = LancamentoDaPesagem(
        api(
          resposta: {
            'print_job': null,
            'command': {'number': 17},
          },
        ),
        accessToken: 't',
      );

      final resultado = await lancamento.lancar(
        balanca: 'bal-1',
        comanda: null,
        pesoKg: 0.5,
        extras: const [],
        imprimir: false,
      );

      final corpo = jsonDecode(chamadas.single.body) as Map<String, dynamic>;
      expect(corpo['comanda_automatica'], isTrue);
      expect(corpo.containsKey('command_code'), isFalse);
      expect(resultado.comanda, '17');
    },
  );

  test('sem trabalho de impressao devolve null', () async {
    final lancamento = LancamentoDaPesagem(
      api(resposta: {'print_job': null}),
      accessToken: 't',
    );

    expect(
      (await lancamento.lancar(
        balanca: 'bal-1',
        comanda: '42',
        pesoKg: 1,
        extras: const [],
        imprimir: false,
      )).printJob,
      isNull,
    );
  });
}
