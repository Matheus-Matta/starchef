import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_desktop/features/home/data/nota_do_pedido.dart';

/// Procurar a nota pelo pedido com a rede e o servidor da loja de verdade:
/// cabo mexido, backend reiniciando, nota ainda pela metade.
void main() {
  const token = 'x.eyJ1c2VyX2lkIjoidTEifQ.y';
  const semEspera = [Duration.zero, Duration.zero, Duration.zero];
  final notaPronta = {
    'id': 'p1',
    'fiscal': {'id': 'n1', 'fiscal_state': 'authorized', 'printable': true},
  };

  http.Response json(Object corpo, [int status = 200]) =>
      http.Response(jsonEncode(corpo), status);

  /// Cada consulta recebe a próxima resposta da lista; a última se repete.
  Future<(Map<String, dynamic>?, int)> procurar(
    List<Object Function()> respostas,
  ) async {
    var consultas = 0;
    final api = ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      cloudFallback: CloudFallback(enabled: false),
      client: MockClient((request) async {
        final atual = respostas[consultas.clamp(0, respostas.length - 1)]();
        consultas++;
        if (atual is Exception) throw atual;
        return atual as http.Response;
      }),
    );
    final nota = await NotaDoPedido(
      api,
      accessToken: token,
      esperas: semEspera,
    ).esperar('p1');
    await api.dispose();
    return (nota, consultas);
  }

  test('o cabo saiu na primeira consulta: acha a nota na seguinte', () async {
    final (nota, _) = await procurar([
      () => const SocketException('rede caiu'),
      () => json(notaPronta),
    ]);

    expect(nota?['id'], 'n1');
  });

  test('backend reiniciando (500, 502) não encerra a procura', () async {
    final (nota, _) = await procurar([
      () => json({'detail': 'erro'}, 500),
      () => http.Response('<html>Bad Gateway</html>', 502),
      () => json(notaPronta),
    ]);

    expect(nota?['printable'], isTrue);
  });

  test(
    'nota pela metade (sem id) ainda não serve: continua esperando',
    () async {
      final (nota, consultas) = await procurar([
        () => json({
          'id': 'p1',
          'fiscal': {'fiscal_state': 'processing'},
        }),
        () => json(notaPronta),
      ]);

      expect(nota?['id'], 'n1');
      expect(consultas, 2);
    },
  );

  test(
    'backend antigo, sem o bloco fiscal: desiste no fim da janela',
    () async {
      final (nota, consultas) = await procurar([
        () => json({'id': 'p1'}),
      ]);

      expect(nota, isNull);
      expect(consultas, semEspera.length + 1, reason: 'não fica preso');
    },
  );

  test('achou na primeira consulta: não consulta de novo', () async {
    final (nota, consultas) = await procurar([() => json(notaPronta)]);

    expect(nota?['id'], 'n1');
    expect(consultas, 1);
  });
}
