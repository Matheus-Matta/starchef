import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';

import 'pdv_test_support.dart';

/// O primeiro item de uma comanda sobe junto com o pedido, em
/// `/orders/create-with-item/`. A resposta é o PEDIDO do servidor, com o item
/// já batizado com o id real — e a cópia local ainda o conhece pelo id
/// temporário. Se essa troca não acontecer, a próxima leitura vinda do
/// servidor trata o item local como "ainda pendente" e o soma de novo: a
/// mesma coxinha duas vezes na conta, e a comanda "enchendo sozinha".
void main() {
  late TestPdvStack stack;
  late FakeSyncTransport transport;
  late SyncService sync;

  setUp(() async {
    stack = await TestPdvStack.create();
    transport = FakeSyncTransport();
    sync = SyncService(gateway: stack.gateway, transport: transport);
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
      {
        'id': 'prod-1',
        'name': 'Coxinha',
        'restaurant': 'rest-1',
        'current_price': '6.00',
        'pricing_unit': 'unit',
      },
    ]);
  });

  tearDown(() async {
    await sync.dispose();
    await stack.dispose();
  });

  List<Map> itemsOf(Map<String, dynamic> order) =>
      (order['items'] as List).cast<Map>();

  Map<String, dynamic> item(String id, {String quantity = '1.000'}) => {
    'id': id,
    'product': 'prod-1',
    'product_name': 'Coxinha',
    'quantity': quantity,
    'unit_price': '6.00',
    'total_price': '6.00',
    'status': 'pending',
  };

  Map<String, dynamic> serverOrder(
    List<Map<String, dynamic>> items, {
    String? createdItemId,
  }) => {
    'id': 'pedido-real',
    'status': 'open',
    'order_type': 'command',
    'command': 'cmd-1',
    'items': items,
    'subtotal': '6.00',
    'total': '6.00',
    'created_item_id': ?createdItemId,
  };

  /// Comanda aberta como rascunho e primeiro item lançado: uma operação
  /// `create-with-item` na fila, com o item sob id temporário.
  Future<String> lancarPrimeiroItem() async {
    final draft = await stack.gateway.write(
      'POST',
      '/orders/open-command/',
      body: {'command': 'cmd-1'},
      context: {
        'command': {'id': 'cmd-1', 'number': 7},
      },
    );
    final localId = '${draft.payload['id']}';
    final created = await stack.gateway.write(
      'POST',
      '/orders/$localId/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );
    final localItemId = '${itemsOf(created.payload).single['id']}';
    expect(localItemId, startsWith('offline-'));
    return localItemId;
  }

  test('primeiro item confirmado não duplica na leitura seguinte', () async {
    await lancarPrimeiroItem();
    transport.handlers['POST /orders/create-with-item/'] = (request) =>
        serverOrder([item('item-real')], createdItemId: 'item-real');
    await sync.push();

    var stored = await stack.gateway.orders.read('pedido-real');
    expect(stored, isNotNull);
    expect(
      itemsOf(stored!.payload).map((entry) => entry['id']),
      ['item-real'],
      reason: 'o id temporário do item precisa virar o real na confirmação',
    );

    // Uma leitura comum do servidor (reconciliação do GET, pull periódico).
    await stack.gateway.orders.applyRemote(serverOrder([item('item-real')]));
    stored = await stack.gateway.orders.read('pedido-real');
    expect(itemsOf(stored!.payload), hasLength(1));
  });

  test('servidor antigo, sem created_item_id: o único item é o lançado', () async {
    await lancarPrimeiroItem();
    transport.handlers['POST /orders/create-with-item/'] = (request) =>
        serverOrder([item('item-real')]);
    await sync.push();

    final stored = await stack.gateway.orders.read('pedido-real');
    expect(
      itemsOf(stored!.payload).map((entry) => entry['id']),
      ['item-real'],
    );
  });

  test('comanda já aberta por outro terminal: o item adota a linha de lá', () async {
    final localItemId = await lancarPrimeiroItem();
    // O servidor somou o lançamento na linha pendente que já existia e
    // devolveu o pedido inteiro, com o que os outros já tinham pedido.
    transport.handlers['POST /orders/create-with-item/'] = (request) =>
        serverOrder([
          item('item-antigo', quantity: '2.000'),
          item('item-outro'),
        ], createdItemId: 'item-antigo');
    await sync.push();

    final stored = await stack.gateway.orders.read('pedido-real');
    final ids = itemsOf(stored!.payload).map((entry) => entry['id']).toList();
    expect(ids, ['item-antigo', 'item-outro']);
    expect(ids, isNot(contains(localItemId)));
    // O mapa de ids sabe para onde o temporário foi: uma operação seguinte
    // que o cite (cancelar, mudar quantidade) resolve para a linha real.
    final resolved = await stack.queue.resolvedIds(scope: TestPdvStack.scope);
    expect(resolved[localItemId], 'item-antigo');
  });

  test('pesagem confirmada troca o pesado e os extras pelos ids reais', () async {
    // A pesagem sobe o item pesado e os extras numa operação só; a resposta é
    // `{order, weighed_item, extra_items}`. Vale a mesma regra: os temporários
    // que a operação criou viram os reais que voltaram.
    await stack.gateway.repository(EntityCatalog.command).applyRemote({
      'id': 'cmd-1',
      'code': 'CMD-7',
      'number': 7,
      'restaurant': 'rest-1',
    });
    final weighed = await stack.gateway.write(
      'POST',
      '/scales/balanca-1/checkout-command/',
      body: {
        'command_code': 'CMD-7',
        'weight_kg': '0.400',
        'extras': [
          {'product': 'prod-1', 'quantity': 1},
        ],
      },
      context: {
        'weighed_product': {
          'id': 'prod-2',
          'name': 'Buffet por quilo',
          'current_price': '59.90',
          'pricing_unit': 'kg',
        },
      },
    );
    final localIds = itemsOf(weighed.payload).map((e) => '${e['id']}').toList();
    expect(localIds, everyElement(startsWith('offline-')));
    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    final body = queued.single.payload!;
    expect(body['client_item_id'], localIds.first);
    expect((body['extras'] as List).single['client_item_id'], localIds.last);

    final pesado = {
      ...item('pesado-real', quantity: '0.400'),
      'product': 'prod-2',
      'pricing_unit': 'kg',
    };
    transport.handlers['POST /scales/balanca-1/checkout-command/'] = (_) => {
      'order': serverOrder([pesado, item('extra-real')]),
      'weighed_item': pesado,
      'extra_items': [item('extra-real')],
      'print_job': null,
    };
    await sync.push();

    var stored = await stack.gateway.orders.read('pedido-real');
    expect(
      itemsOf(stored!.payload).map((e) => e['id']),
      ['pesado-real', 'extra-real'],
    );
    await stack.gateway.orders.applyRemote(
      serverOrder([pesado, item('extra-real')]),
    );
    stored = await stack.gateway.orders.read('pedido-real');
    expect(itemsOf(stored!.payload), hasLength(2));
  });
}
