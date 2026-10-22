import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_desktop/features/home/data/pdv_repository.dart';
import 'package:starchef_pdv_desktop/features/home/data/produtos_em_paginas.dart';

/// A venda abre com a PRIMEIRA página de produtos; o resto vem por trás.
///
/// O catálogo esperava todas as páginas (5 a 7 s na nuvem) antes de mostrar
/// a grade.
void main() {
  late List<int> paginasPedidas;

  PdvRepository repositorio({required int paginas}) {
    paginasPedidas = [];
    final api = ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      cloudFallback: CloudFallback(enabled: false),
      client: MockClient((request) async {
        final pagina = int.parse(request.url.queryParameters['page']!);
        paginasPedidas.add(pagina);
        return http.Response(
          jsonEncode({
            'results': [
              {'id': 'p$pagina', 'name': 'Produto $pagina'},
            ],
            'next': pagina < paginas
                ? 'http://loja.local/?page=${pagina + 1}'
                : null,
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );
    addTearDown(api.dispose);
    return PdvRepository(api: api, accessToken: 't');
  }

  test('volta com a primeira página e busca o resto por trás', () async {
    final repo = repositorio(paginas: 3);
    final avisos = <String>[];
    repo.api.signals.changes.listen(avisos.add);

    final primeira = await produtosDaPrimeiraPagina(
      repo,
      '/menu/products/',
      const {'page_size': 60},
    );

    expect(primeira.itens.map((p) => p['id']), ['p1']);
    expect(primeira.incompleto, isTrue);

    await Future<void>.delayed(const Duration(milliseconds: 300));
    expect(paginasPedidas, [1, 2, 3]);
    expect(avisos, contains('realtime:menu'));
  });

  test('cardápio de uma página só não deixa nada por trás', () async {
    final repo = repositorio(paginas: 1);

    final primeira = await produtosDaPrimeiraPagina(
      repo,
      '/menu/products/',
      const {'page_size': 60},
    );

    expect(primeira.incompleto, isFalse);
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(paginasPedidas, [1]);
  });
}
