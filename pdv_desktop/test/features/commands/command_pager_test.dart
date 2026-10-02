import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_listing.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_pager.dart';

/// Uma loja de [total] comandas, servida de [tamanho] em [tamanho].
({List<String> pedidos, BuscarPaginaDeComandas buscar}) _loja(
  int total, {
  int tamanho = 50,
}) {
  final pedidos = <String>[];
  Future<PaginaDeComandas> buscar({
    required int pagina,
    String busca = '',
  }) async {
    pedidos.add('$pagina:$busca');
    final todas = [
      for (var n = 1; n <= total; n++)
        if (busca.isEmpty || '$n'.contains(busca)) {'id': 'c$n', 'number': n},
    ];
    final inicio = (pagina - 1) * tamanho;
    final fim = (inicio + tamanho).clamp(0, todas.length);
    return (
      itens: inicio >= todas.length
          ? <Map<String, dynamic>>[]
          : todas.sublist(inicio, fim),
      temMais: fim < todas.length,
      total: todas.length,
    );
  }

  return (pedidos: pedidos, buscar: buscar);
}

List<Object?> _numeros(CommandPager p) =>
    p.itens.map((c) => c['number']).toList();

void main() {
  test('desce página por página e para no fim', () async {
    final loja = _loja(120);
    final pager = CommandPager(loja.buscar);

    await pager.recomecar();
    expect(pager.itens, hasLength(50));
    expect(pager.temMais, isTrue);
    expect(pager.total, 120);

    await pager.carregarMais();
    await pager.carregarMais();
    expect(pager.itens, hasLength(120));
    expect(_numeros(pager).last, 120);
    expect(pager.temMais, isFalse);

    await pager.carregarMais();
    expect(loja.pedidos, ['1:', '2:', '3:'], reason: 'no fim não pede mais');
  });

  test('rolagem rápida não pede a mesma página duas vezes', () async {
    final loja = _loja(120);
    final pager = CommandPager(loja.buscar);
    await pager.recomecar();

    // A rolagem dispara o aviso de "perto do fim" várias vezes seguidas.
    await Future.wait([pager.carregarMais(), pager.carregarMais()]);

    expect(loja.pedidos, ['1:', '2:']);
    expect(pager.itens, hasLength(100));
  });

  test('resposta de uma busca velha não troca a lista da nova', () async {
    // Digitar "1" e depois "12": o "1" casa com mais e chega por ÚLTIMO.
    final lenta = Completer<PaginaDeComandas>();
    final pager = CommandPager(({required int pagina, String busca = ''}) {
      if (busca == '1') return lenta.future;
      return Future.value((
        itens: [
          {'id': 'c12', 'number': 12},
        ],
        temMais: false,
        total: 1,
      ));
    });

    final primeira = pager.recomecar(busca: '1');
    await pager.recomecar(busca: '12');
    lenta.complete((
      itens: [
        {'id': 'c1', 'number': 1},
        {'id': 'c10', 'number': 10},
      ],
      temMais: true,
      total: 40,
    ));
    await primeira;

    expect(_numeros(pager), [12]);
    expect(pager.total, 1);
    expect(pager.carregando, isFalse);
  });

  test('comanda repetida entre páginas aparece uma vez só', () async {
    // Uma comanda criada no meio da rolagem empurra tudo uma posição: a
    // última da página 1 volta como primeira da página 2.
    final pager = CommandPager(
      ({required int pagina, String busca = ''}) async => (
        itens: pagina == 1
            ? [
                {'id': 'a', 'number': 1},
                {'id': 'b', 'number': 2},
              ]
            : [
                {'id': 'b', 'number': 2},
                {'id': 'c', 'number': 3},
              ],
        temMais: pagina == 1,
        total: 3,
      ),
    );

    await pager.recomecar();
    await pager.carregarMais();

    expect(_numeros(pager), [1, 2, 3]);
  });

  test(
    'falha na página 2 mantém a 1 e "tentar de novo" continua dali',
    () async {
      var falhar = true;
      final loja = _loja(80);
      final pager = CommandPager(({required int pagina, String busca = ''}) {
        if (pagina == 2 && falhar) throw const ApiException('Sem conexão');
        return loja.buscar(pagina: pagina, busca: busca);
      });

      await pager.recomecar();
      await pager.carregarMais();
      expect(pager.erro, 'Sem conexão');
      expect(pager.itens, hasLength(50), reason: 'a página 1 continua na tela');

      // Com erro, a rolagem não insiste sozinha (seria um laço de pedidos).
      await pager.carregarMais();
      expect(loja.pedidos, ['1:']);

      falhar = false;
      await pager.tentarDeNovo();
      expect(pager.erro, isEmpty);
      expect(pager.itens, hasLength(80));
      expect(loja.pedidos, ['1:', '2:']);
    },
  );

  test('falha que não é ApiException também vira recado', () async {
    final pager = CommandPager(
      ({required int pagina, String busca = ''}) =>
          throw StateError('rede caiu'),
    );

    await pager.recomecar();

    expect(pager.erro, contains('rede caiu'));
    expect(pager.carregando, isFalse);
  });

  test('digitar espera parar de digitar e busca uma vez', () async {
    final loja = _loja(300);
    final pager = CommandPager(
      loja.buscar,
      espera: const Duration(milliseconds: 30),
    );

    pager.digitar('1');
    pager.digitar('12');
    pager.digitar('120');
    await Future<void>.delayed(const Duration(milliseconds: 80));

    expect(loja.pedidos, ['1:120']);
    expect(_numeros(pager), [120]);
  });

  test('buscarJa não espera: é o Enter do leitor', () async {
    final loja = _loja(300);
    final pager = CommandPager(loja.buscar, espera: const Duration(seconds: 5));

    pager.digitar('7');
    await pager.buscarJa('77');

    expect(loja.pedidos, ['1:77']);
    expect(_numeros(pager), [77, 177, 277]);
  });

  test('atualizar troca só a comanda que mudou', () async {
    final pager = CommandPager(_loja(3).buscar);
    await pager.recomecar();

    pager.atualizar({'id': 'c2', 'number': 2, 'status': 'occupied'});
    pager.atualizar({'id': 'fora', 'number': 999});

    expect(pager.itens[1]['status'], 'occupied');
    expect(pager.itens, hasLength(3));
  });

  group('a página no servidor', () {
    test('pede 50, por número, com a busca e o restaurante', () async {
      late Uri pedido;
      final api = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        client: MockClient((request) async {
          pedido = request.url;
          return http.Response(
            jsonEncode({
              'count': 3,
              'next': 'http://starchef.test/api/v1/commands/?page=3',
              'results': [
                {'id': 'c12', 'number': 12},
              ],
            }),
            200,
          );
        }),
      );

      final pagina = await paginaDeComandas(
        api,
        pagina: 2,
        busca: ' 12 ',
        restaurantId: 'r1',
      );

      expect(pedido.queryParameters, {
        'page_size': '50',
        'page': '2',
        'is_active': 'true',
        'ordering': 'number',
        'restaurant': 'r1',
        'search': '12',
      });
      expect(pagina.itens.single['number'], 12);
      expect(pagina.temMais, isTrue);
      expect(pagina.total, 3);
    });

    test('sem busca, não manda "search"', () async {
      late Uri pedido;
      final api = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        client: MockClient((request) async {
          pedido = request.url;
          return http.Response('{"results": [], "next": null}', 200);
        }),
      );

      final pagina = await paginaDeComandas(api, pagina: 1);

      expect(pedido.queryParameters.containsKey('search'), isFalse);
      expect(pagina.temMais, isFalse);
    });

    test('formato desconhecido é erro, não lista vazia', () async {
      final api = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        client: MockClient((_) async => http.Response('{"results": 1}', 200)),
      );

      await expectLater(
        paginaDeComandas(api, pagina: 1),
        throwsA(isA<ApiException>()),
      );
    });
  });
}
