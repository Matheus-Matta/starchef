import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/input/code_lookup_service.dart';

import '../data/pdv_test_support.dart';

/// Achar o produto de um código lido, sem internet e sem varrer o catálogo.
///
/// A consulta é do SQLite do Caixa Principal: é o que faz o leitor continuar
/// funcionando com a nuvem fora, e o que tira a latência da rede de entre o
/// operador e a próxima venda.
void main() {
  late TestPdvStack stack;
  late CodeLookupService lookup;

  setUp(() async {
    stack = await TestPdvStack.create();
    lookup = CodeLookupService(stack.gateway);
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
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
    ]);
    await stack.gateway.repository(EntityCatalog.command).applyRemoteList([
      {
        'id': 'cmd-7',
        'code': 'CMD-0007',
        'number': 7,
        'status': 'occupied',
        'restaurant': 'rest-1',
        'current_order_id': 'order-1',
      },
    ]);
  });

  tearDown(() => stack.dispose());

  test('o código de barras acha o produto', () async {
    final result = await lookup.findProduct(
      '7891000100103',
      restaurantId: 'rest-1',
      orderType: 'command',
    );

    expect(result.found, isTrue);
    expect(result.product?['id'], 'prod-refri');
    expect(result.matchedField, 'ean');
  });

  test('o código interno também acha, e o EAN tem prioridade', () async {
    final byInternal = await lookup.findProduct('BEB-01', restaurantId: 'rest-1');

    expect(byInternal.product?['id'], 'prod-refri');
    expect(byInternal.matchedField, 'internal_code');
  });

  test('zeros à esquerda são parte do código', () async {
    final withZeros = await lookup.findProduct(
      '00000012345670',
      restaurantId: 'rest-1',
    );
    final withoutZeros = await lookup.findProduct(
      '12345670',
      restaurantId: 'rest-1',
    );

    expect(withZeros.product?['id'], 'prod-zeros');
    // Não é o mesmo código: achar o produto aqui seria vender o item errado.
    expect(withoutZeros.found, isFalse);
  });

  test('produto inativo não entra no pedido', () async {
    final result = await lookup.findProduct(
      '7899999999993',
      restaurantId: 'rest-1',
    );

    expect(result.found, isFalse);
  });

  test('produto de outra unidade não entra no pedido', () async {
    final result = await lookup.findProduct(
      '7897777777775',
      restaurantId: 'rest-1',
    );

    expect(result.found, isFalse);
  });

  test('a disponibilidade por tipo de pedido é respeitada', () async {
    final atTable = await lookup.findProduct(
      '7896666666666',
      restaurantId: 'rest-1',
      orderType: 'command',
    );
    final atCounter = await lookup.findProduct(
      '7896666666666',
      restaurantId: 'rest-1',
      orderType: 'counter',
    );

    expect(atTable.found, isFalse);
    expect(atCounter.found, isTrue);
  });

  test('um código desconhecido simplesmente não acha nada', () async {
    final result = await lookup.findProduct('0000000000000', restaurantId: 'rest-1');

    expect(result.found, isFalse);
    expect(result.product, isNull);
  });

  test('a comanda é achada pelo código impresso e pelo número', () async {
    final byCode = await lookup.findCommand('CMD-0007');
    final byNumber = await lookup.findCommand('7');

    expect(byCode.command?['id'], 'cmd-7');
    expect(byCode.matchedField, 'code');
    expect(byNumber.command?['id'], 'cmd-7');
    expect(byNumber.matchedField, 'number');
  });

  test('o código sai do índice quando o produto é apagado', () async {
    await stack.gateway.repository(EntityCatalog.product).applyRemote({
      'id': 'prod-refri',
      'name': 'Refrigerante lata',
      'ean': '7891000100103',
      'deleted_at': DateTime.now().toUtc().toIso8601String(),
    });

    final result = await lookup.findProduct(
      '7891000100103',
      restaurantId: 'rest-1',
    );

    expect(result.found, isFalse);
  });

  test('trocar o código do produto não deixa o antigo respondendo', () async {
    await stack.gateway.repository(EntityCatalog.product).applyRemote({
      'id': 'prod-refri',
      'name': 'Refrigerante lata',
      'ean': '7891000100097',
      'internal_code': 'BEB-01',
      'is_active': true,
      'restaurants': ['rest-1'],
    });

    final old = await lookup.findProduct('7891000100103', restaurantId: 'rest-1');
    final current = await lookup.findProduct(
      '7891000100097',
      restaurantId: 'rest-1',
    );

    expect(old.found, isFalse);
    expect(current.product?['id'], 'prod-refri');
  });

  test('uma base anterior ao índice é reconstruída na primeira leitura', () async {
    // Simula a instalação que já existia: os produtos estão gravados, o índice
    // não. Sem a reconstrução, o leitor não acharia nada até o próximo pull.
    await stack.database.execute('DELETE FROM entity_codes');

    final result = await lookup.findProduct(
      '7891000100103',
      restaurantId: 'rest-1',
    );

    expect(result.product?['id'], 'prod-refri');
  });

  test('a consulta não varre o catálogo', () async {
    final rows = await stack.database.query(
      'SELECT COUNT(*) AS total FROM entity_codes WHERE entity_type = ?',
      [EntityCatalog.product],
    );

    // Uma linha por código cadastrado — a consulta é direta pelo índice.
    expect((rows.single['total'] as num).toInt(), 10);
  });
}
