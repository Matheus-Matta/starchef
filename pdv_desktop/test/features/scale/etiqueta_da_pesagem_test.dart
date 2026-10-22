import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/print_document.dart';
import 'package:starchef_pdv_desktop/features/scale/data/etiqueta_da_pesagem.dart';

/// A Balança Rápida imprime a PRÓPRIA etiqueta e confirma no servidor.
///
/// Antes ela só criava o trabalho e esperava um PDV imprimir. Com a impressora
/// USB/serial ligada no PC da balança, outro PC reservava o trabalho, tentava
/// a porta dele e a etiqueta não saía.
void main() {
  late List<http.Request> chamadas;

  ApiClient api() {
    chamadas = [];
    return ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((request) async {
        chamadas.add(request);
        return http.Response(
          jsonEncode({'id': 'job-1', 'status': 'ok'}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
  }

  const job = {
    'id': 'job-1',
    'printer': 'imp-1',
    'job_type': 'weigh_ticket',
    'payload': {'text_content': 'COMANDA 17\nTOTAL 26,95'},
  };
  const impressora = {
    'id': 'imp-1',
    'name': 'Balança 1',
    'connection_type': 'serial',
    'endpoint': '/dev/ttyUSB0',
  };

  test('imprime aqui e marca como impressa', () async {
    final enviados = <PrintDocument>[];
    final etiqueta = EtiquetaDaPesagem(
      api(),
      accessToken: 't',
      enviar: (_, documento) async => enviados.add(documento),
    );

    await etiqueta.imprimir(job: job, impressora: impressora);
    await etiqueta.confirmando;

    expect(enviados.single.content, contains('COMANDA 17'));
    expect(
      chamadas.single.url.path,
      endsWith('/print-jobs/job-1/mark-printed/'),
    );
  });

  test('a impressora falhou: marca a falha com o motivo e avisa', () async {
    final etiqueta = EtiquetaDaPesagem(
      api(),
      accessToken: 't',
      enviar: (_, _) async => throw StateError('sem papel'),
    );

    await expectLater(
      etiqueta.imprimir(job: job, impressora: impressora),
      throwsA(
        isA<FalhaNaEtiqueta>().having(
          (f) => f.motivo,
          'motivo',
          contains('sem papel'),
        ),
      ),
    );
    expect(
      chamadas.single.url.path,
      endsWith('/print-jobs/job-1/mark-failed/'),
    );
    expect(jsonDecode(chamadas.single.body)['error'], contains('sem papel'));
  });

  test('sem a impressora cadastrada neste terminal: falha explicada', () async {
    var enviou = false;
    final etiqueta = EtiquetaDaPesagem(
      api(),
      accessToken: 't',
      enviar: (_, _) async => enviou = true,
    );

    await expectLater(
      etiqueta.imprimir(job: job, impressora: null),
      throwsA(isA<FalhaNaEtiqueta>()),
    );
    expect(enviou, isFalse);
    expect(
      chamadas.single.url.path,
      endsWith('/print-jobs/job-1/mark-failed/'),
    );
  });
}
