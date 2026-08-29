import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';

import 'pdv_test_support.dart';

/// Itens pendentes iguais viram UMA linha, na hora.
///
/// O servidor já agrupava; a tela offline só descobria isso na sincronização, e
/// até lá mostrava linhas repetidas que depois se fundiam sozinhas. Com o
/// leitor isso deixa de ser detalhe: bipar cinco vezes o mesmo refrigerante
/// encheria a comanda de cinco linhas de quantidade 1.
void main() {
  late TestPdvStack stack;

  List<Map<String, dynamic>> itemsOf(Map<String, dynamic> order) =>
      (order['items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();

  setUp(() async {
    stack = await TestPdvStack.create();
    stack.gateway.connectivity = () => false;
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
      {
        'id': 'prod-refri',
        'name': 'Refrigerante lata',
        'sale_price': '7.50',
        'current_price': '7.50',
        'pricing_unit': 'unit',
        'is_active': true,
        'variations': [
          {'id': 'var-gelada', 'name': 'Gelada', 'price_delta': '0.00', 'is_active': true},
        ],
        'addons': const [],
      },
      {
        'id': 'prod-kg',
        'name': 'Buffet por quilo',
        'sale_price': '69.90',
        'current_price': '69.90',
        'pricing_unit': 'kg',
        'is_active': true,
      },
    ]);
    await stack.gateway.repository(EntityCatalog.order).applyRemote({
      'id': 'order-1',
      'restaurant': 'rest-1',
      'sequence': 42,
      'status': 'open',
      'items': const [],
    });
  });

  tearDown(() => stack.dispose());

  Future<Map<String, dynamic>> addItem({
    String product = 'prod-refri',
    List<String> variations = const [],
    String note = '',
    num quantity = 1,
  }) async {
    final result = await stack.gateway.write(
      'POST',
      '/orders/order-1/items/',
      body: {
        'product': product,
        'quantity': quantity,
        'variations': variations,
        'addons': const [],
        'customer_note': note,
      },
    );
    return result.payload;
  }

  test('lançar o mesmo produto duas vezes soma na mesma linha', () async {
    await addItem();
    final order = await addItem();

    final items = itemsOf(order);
    expect(items, hasLength(1));
    expect(items.single['quantity'], 2);
  });

  test('o total da linha acompanha a quantidade', () async {
    await addItem();
    final order = await addItem();

    final item = itemsOf(order).single;
    expect(item['total_price'], 15.0);
  });

  test('variação diferente é outra linha', () async {
    await addItem();
    final order = await addItem(variations: ['var-gelada']);

    expect(itemsOf(order), hasLength(2));
  });

  test('observação diferente é outra linha', () async {
    await addItem(note: 'sem gelo');
    final order = await addItem(note: 'com gelo');

    expect(itemsOf(order), hasLength(2));
  });

  test('a mesma observação junta', () async {
    await addItem(note: 'sem gelo');
    final order = await addItem(note: 'sem gelo');

    expect(itemsOf(order), hasLength(1));
    expect(itemsOf(order).single['quantity'], 2);
  });

  test('item já enviado à cozinha não recebe mais quantidade', () async {
    await addItem();
    // A rodada foi para a produção: mexer na quantidade dela mudaria o que a
    // cozinha já recebeu.
    final sent = await stack.gateway.repository(EntityCatalog.order).read('order-1');
    final items = itemsOf(sent!.payload)
        .map((item) => {...item, 'status': 'sent'})
        .toList();
    await stack.gateway.repository(EntityCatalog.order).applyRemote({
      ...sent.payload,
      'items': items,
    }, overwriteLocalChanges: true);

    final order = await addItem();

    expect(itemsOf(order), hasLength(2));
  });

  test('produto por peso nunca é agrupado', () async {
    await addItem(product: 'prod-kg', quantity: 0.412);
    final order = await addItem(product: 'prod-kg', quantity: 0.508);

    // Cada pesagem é uma leitura própria; somá-las apagaria o registro de duas
    // idas à balança.
    expect(itemsOf(order), hasLength(2));
  });

  test('cada lançamento continua sendo uma operação na fila', () async {
    await addItem();
    await addItem();

    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    // Agrupar na tela não pode esconder do servidor que houve dois
    // lançamentos: ele agrupa por conta dele, com a própria regra.
    expect(
      queued.where((entry) => entry.path == '/orders/order-1/items/').length,
      2,
    );
  });
}
