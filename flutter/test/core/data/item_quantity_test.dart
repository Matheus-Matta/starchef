import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';

import 'pdv_test_support.dart';

/// `+` e `-` sobre o item selecionado, sem internet.
///
/// A regra é a mesma do servidor, e ela existe por um motivo: um item já
/// despachado descreve o que a cozinha recebeu. Mudar a quantidade dele
/// reescreveria o passado sem ninguém na produção ficar sabendo.
void main() {
  late TestPdvStack stack;

  List<Map<String, dynamic>> itemsOf(Map<String, dynamic> order) =>
      (order['items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();

  Future<Map<String, dynamic>> setQuantity(String itemId, num quantity) async {
    final result = await stack.gateway.write(
      'POST',
      '/orders/order-1/items/$itemId/quantity/',
      body: {'quantity': quantity},
    );
    return result.payload;
  }

  setUp(() async {
    stack = await TestPdvStack.create();
    stack.gateway.connectivity = () => false;
    await stack.gateway.repository(EntityCatalog.order).applyRemote({
      'id': 'order-1',
      'restaurant': 'rest-1',
      'status': 'open',
      'items': [
        {
          'id': 'item-pendente',
          'product': 'prod-1',
          'product_name': 'Refrigerante lata',
          'status': 'pending',
          'pricing_unit': 'unit',
          'quantity': 2,
          'unit_price': 7.5,
          'total_price': 15.0,
          'addons': [
            {'addon': 'add-1', 'unit_price': 2.0, 'total_price': 4.0},
          ],
        },
        {
          'id': 'item-enviado',
          'product': 'prod-1',
          'product_name': 'Refrigerante lata',
          'status': 'sent',
          'pricing_unit': 'unit',
          'quantity': 1,
          'unit_price': 7.5,
          'total_price': 7.5,
        },
        {
          'id': 'item-peso',
          'product': 'prod-kg',
          'product_name': 'Buffet',
          'status': 'pending',
          'pricing_unit': 'kg',
          'quantity': 0.412,
          'unit_price': 69.9,
          'total_price': 28.8,
        },
      ],
    });
  });

  tearDown(() => stack.dispose());

  test('a quantidade muda e o total da linha acompanha', () async {
    final order = await setQuantity('item-pendente', 3);

    final item = itemsOf(order).firstWhere(
      (entry) => entry['id'] == 'item-pendente',
    );
    expect(item['quantity'], 3);
    expect(item['total_price'], 22.5);
  });

  test('os adicionais são recalculados junto', () async {
    final order = await setQuantity('item-pendente', 3);

    final item = itemsOf(order).firstWhere(
      (entry) => entry['id'] == 'item-pendente',
    );
    final addon = (item['addons'] as List).first as Map;
    expect(addon['total_price'], 6.0);
  });

  test('item já enviado à cozinha é recusado', () async {
    await expectLater(
      setQuantity('item-enviado', 5),
      throwsA(isA<ArgumentError>()),
    );
  });

  test('produto por peso é recusado', () async {
    // A quantidade dele vem da balança, não do teclado.
    await expectLater(
      setQuantity('item-peso', 1),
      throwsA(isA<ArgumentError>()),
    );
  });

  test('zero é recusado: remover exige o cancelamento', () async {
    await expectLater(
      setQuantity('item-pendente', 0),
      throwsA(isA<ArgumentError>()),
    );
  });

  test('a alteração entra na fila com a quantidade final', () async {
    await setQuantity('item-pendente', 3);
    await setQuantity('item-pendente', 4);

    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    final changes = queued
        .where((entry) => entry.path.endsWith('/quantity/'))
        .toList();
    // O corpo carrega a quantidade FINAL, não um incremento: reenviar a mesma
    // operação leva ao mesmo resultado.
    expect(changes.last.payload!['quantity'], 4);
  });
}
