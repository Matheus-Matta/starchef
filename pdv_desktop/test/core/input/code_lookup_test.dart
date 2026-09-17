import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/input/code_lookup_service.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';

/// Achar o produto (ou a comanda) de um código lido.
///
/// Quem responde é o servidor — o mesmo cadastro que a retaguarda edita. O
/// cuidado que estes testes guardam é o oposto do que existia no PDV offline:
/// lá o risco era um índice local envelhecido; aqui é a BUSCA DO SERVIDOR ser
/// generosa demais. `/products/?search=` casa nome e descrição também, e um
/// código lido que caísse num nome parecido venderia o item errado.
void main() {
  late ApiClient api;
  late List<Uri> chamadas;

  final produtos = <Map<String, dynamic>>[
    {
      'id': 'prod-refri',
      'name': 'Refrigerante lata',
      'ean': '7891000100103',
      'internal_code': 'BEB-01',
      'is_active': true,
      'restaurants': ['rest-1'],
      'available_for_table': true,
      'available_for_counter': true,
    },
    {
      'id': 'prod-zeros',
      'name': 'Etiqueta com zeros',
      'ean': '00000012345670',
      'internal_code': 'ETQ-1',
      'is_active': true,
      'restaurants': ['rest-1'],
    },
    {
      'id': 'prod-inativo',
      'name': 'Produto fora de linha',
      'ean': '7899999999993',
      'internal_code': 'OLD-1',
      'is_active': false,
      'restaurants': ['rest-1'],
    },
    {
      'id': 'prod-outra-unidade',
      'name': 'Só da outra loja',
      'ean': '7897777777775',
      'internal_code': 'OUT-1',
      'is_active': true,
      'restaurants': ['rest-2'],
    },
    {
      'id': 'prod-so-balcao',
      'name': 'Combo de balcão',
      'ean': '7896666666666',
      'internal_code': 'CMB-1',
      'is_active': true,
      'restaurants': ['rest-1'],
      'available_for_table': false,
      'available_for_counter': true,
    },
    {
      // O nome contém "500", e nada mais neste produto casa com esse código.
      'id': 'prod-agua',
      'name': 'Água 500ml',
      'ean': '7895555555552',
      'internal_code': 'AGU-1',
      'is_active': true,
      'restaurants': ['rest-1'],
    },
  ];

  final comandas = <Map<String, dynamic>>[
    {
      'id': 'cmd-7',
      'code': 'CMD-0007',
      'number': 7,
      'status': 'occupied',
      'restaurant': 'rest-1',
      'current_order_id': 'order-1',
    },
  ];

  /// Imita a busca do DRF: `search` casa qualquer trecho de nome, código
  /// interno, descrição ou EAN — sem âncora e sem prioridade.
  List<Map<String, dynamic>> busca(
    List<Map<String, dynamic>> fonte,
    String termo,
    List<String> campos,
  ) => fonte
      .where(
        (item) => campos.any(
          (campo) =>
              '${item[campo] ?? ''}'.toLowerCase().contains(termo.toLowerCase()),
        ),
      )
      .toList();

  setUp(() {
    chamadas = [];
    api = ApiClient(
      baseUrl: 'https://servidor.test/api/v1',
      client: MockClient((request) async {
        chamadas.add(request.url);
        final termo = request.url.queryParameters['search'] ?? '';
        // Caminho EXATO, nao sufixo: `endsWith('/products/')` tambem casava
        // `/menu/products/`, e foi assim que uma rota errada (`/products/`,
        // que o backend nao tem) passou pelo teste e so apareceria como 404 no
        // primeiro bipe de codigo de barras do operador.
        if (request.url.path == '/api/v1/menu/products/') {
          return http.Response(
            jsonEncode({
              'results': busca(produtos, termo, [
                'name',
                'internal_code',
                'ean',
              ]),
            }),
            200,
            headers: const {'content-type': 'application/json'},
          );
        }
        if (request.url.path == '/api/v1/commands/by-code/') {
          final code = request.url.queryParameters['code'] ?? '';
          final achada = comandas
              .where((item) => '${item['code']}' == code)
              .toList();
          if (achada.isEmpty) {
            return http.Response(
              jsonEncode({'detail': 'Comanda não encontrada.'}),
              404,
              headers: const {'content-type': 'application/json'},
            );
          }
          return http.Response(
            jsonEncode(achada.single),
            200,
            headers: const {'content-type': 'application/json'},
          );
        }
        if (request.url.path == '/api/v1/commands/') {
          return http.Response(
            jsonEncode({
              'results': busca(comandas, termo, [
                'code',
                'number',
                'customer_name',
              ]),
            }),
            200,
            headers: const {'content-type': 'application/json'},
          );
        }
        // Uma rota que o backend nao tem responde 404 — igual ao servidor de
        // verdade. E o que faz o teste falhar em vez de passar em silencio.
        return http.Response(
          jsonEncode({'detail': 'Rota nao encontrada: ${request.url.path}'}),
          404,
          headers: const {'content-type': 'application/json'},
        );
      }),
    );
  });

  tearDown(() => api.dispose());

  CodeLookupService lookup() => CodeLookupService(api, accessToken: 'token');

  test('o código de barras acha o produto', () async {
    final result = await lookup().findProduct(
      '7891000100103',
      restaurantId: 'rest-1',
      orderType: 'command',
    );

    expect(result.found, isTrue);
    expect(result.product?['id'], 'prod-refri');
    expect(result.matchedField, 'ean');
  });

  test('o código interno também acha, e o EAN tem prioridade', () async {
    final byInternal = await lookup().findProduct(
      'BEB-01',
      restaurantId: 'rest-1',
    );

    expect(byInternal.product?['id'], 'prod-refri');
    expect(byInternal.matchedField, 'internal_code');
  });

  test('um nome que contém o código lido não vira venda', () async {
    // A busca do servidor devolve "Água 500ml" para o termo "500". Sem o
    // filtro por campo exato, bipar 500 venderia a água.
    final result = await lookup().findProduct('500', restaurantId: 'rest-1');

    expect(result.found, isFalse);
  });

  test('zeros à esquerda são parte do código', () async {
    final withZeros = await lookup().findProduct(
      '00000012345670',
      restaurantId: 'rest-1',
    );
    final withoutZeros = await lookup().findProduct(
      '12345670',
      restaurantId: 'rest-1',
    );

    expect(withZeros.product?['id'], 'prod-zeros');
    // Não é o mesmo código: achar o produto aqui seria vender o item errado.
    expect(withoutZeros.found, isFalse);
  });

  test('produto inativo não entra no pedido', () async {
    final result = await lookup().findProduct(
      '7899999999993',
      restaurantId: 'rest-1',
    );

    expect(result.found, isFalse);
  });

  test('produto de outra unidade não entra no pedido', () async {
    final result = await lookup().findProduct(
      '7897777777775',
      restaurantId: 'rest-1',
    );

    expect(result.found, isFalse);
  });

  test('a disponibilidade por tipo de pedido é respeitada', () async {
    final atTable = await lookup().findProduct(
      '7896666666666',
      restaurantId: 'rest-1',
      orderType: 'command',
    );
    final atCounter = await lookup().findProduct(
      '7896666666666',
      restaurantId: 'rest-1',
      orderType: 'counter',
    );

    expect(atTable.found, isFalse);
    expect(atCounter.found, isTrue);
  });

  test('um código desconhecido simplesmente não acha nada', () async {
    final result = await lookup().findProduct(
      '0000000000000',
      restaurantId: 'rest-1',
    );

    expect(result.found, isFalse);
    expect(result.product, isNull);
  });

  test('a unidade recorta a consulta no próprio servidor', () async {
    await lookup().findProduct('7891000100103', restaurantId: 'rest-1');

    // Filtrar aqui e no servidor não é redundância: sem o parâmetro, uma rede
    // com dezenas de lojas devolveria páginas de produtos que este caixa não
    // vende, e o item certo poderia nem caber na primeira página.
    expect(chamadas.single.queryParameters['restaurant'], 'rest-1');
  });

  test('a comanda é achada pelo código impresso e pelo número', () async {
    final byCode = await lookup().findCommand('CMD-0007');
    final byNumber = await lookup().findCommand('7');

    expect(byCode.command?['id'], 'cmd-7');
    expect(byCode.matchedField, 'code');
    expect(byNumber.command?['id'], 'cmd-7');
    expect(byNumber.matchedField, 'number');
  });

  test('o 404 da rota de comanda não é erro, é "não é comanda"', () async {
    // Um EAN de produto lido na tela inicial passa por aqui. Ele não pode
    // estourar exceção nenhuma: o operador continua bipando.
    final result = await lookup().findCommand('7891000100103');

    expect(result.found, isFalse);
  });

  test('o código vazio nem chega ao servidor', () async {
    final result = await lookup().findProduct('   ', restaurantId: 'rest-1');

    expect(result.found, isFalse);
    expect(chamadas, isEmpty);
  });
}
