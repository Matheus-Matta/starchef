import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_desktop/features/scale/data/id_da_pesagem.dart';
import 'package:starchef_pdv_desktop/features/scale/data/lancamento_da_pesagem.dart';

/// "Tentar de novo" é a MESMA pesagem — não um prato novo.
///
/// O identificador nascia dentro de cada tentativa. A rede caía DEPOIS de o
/// servidor gravar, a tela mostrava "a comanda não pôde ser fechada", o
/// operador tentava de novo e ia um identificador novo: o servidor via outro
/// prato. Na comanda lida, dois pratos no cartão; na automática, o prato numa
/// SEGUNDA comanda. Com o mesmo identificador, o servidor reconhece a
/// repetição (`pesagem_por_uuid.py`) e devolve o lançamento que já fez.
void main() {
  test('o mesmo prato tem o mesmo identificador em cada tentativa', () {
    final ids = IdDaPesagem();
    final prato = Object();

    expect(ids.para(prato), ids.para(prato));
  });

  test('o prato seguinte ganha identificador novo', () {
    final ids = IdDaPesagem();
    final primeiro = ids.para(Object());

    expect(ids.para(Object()), isNot(primeiro));
  });

  test(
    'lançado com sucesso, o mesmo prato pesado de novo é outro lançamento',
    () {
      // "Pesar de novo" (R): o peso igual ao do prato lançado é um prato NOVO.
      final ids = IdDaPesagem();
      final prato = Object();
      final lancado = ids.para(prato);

      ids.esquecer();

      expect(ids.para(prato), isNot(lancado));
    },
  );

  test('a repetição vai ao servidor com o identificador da primeira', () async {
    final enviados = <String>[];
    var tentativa = 0;
    final api = ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      cloudFallback: CloudFallback(enabled: false),
      client: MockClient((request) async {
        enviados.add('${(jsonDecode(request.body) as Map)['id']}');
        if (++tentativa == 1) {
          return http.Response('{"detail": "Erro interno"}', 500);
        }
        return http.Response(
          '{"command": {"number": 7}, "print_job": null}',
          201,
        );
      }),
    );
    final ids = IdDaPesagem();
    final prato = Object();
    Future<void> lancar() => LancamentoDaPesagem(api, accessToken: 't').lancar(
      id: ids.para(prato),
      balanca: 'b1',
      comanda: '7',
      pesoKg: 0.452,
      extras: const [],
      imprimir: false,
    );

    await expectLater(lancar(), throwsA(isA<Object>()));
    await lancar();

    expect(enviados, hasLength(2));
    expect(enviados[0], enviados[1]);
    await api.dispose();
  });
}
