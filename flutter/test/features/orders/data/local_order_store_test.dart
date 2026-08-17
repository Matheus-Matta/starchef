import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/orders/data/local_order_store.dart';

const _scope = 'starchef.test|acc-1';

Map<String, dynamic> order({
  String id = 'order-1',
  List<Map<String, dynamic>> items = const [],
  String serviceFee = '0.00',
  String discount = '0.00',
  String restaurant = 'rest-1',
}) => {
  'id': id,
  'restaurant': restaurant,
  'sequence': 42,
  'service_fee': serviceFee,
  'delivery_fee': '0.00',
  'discount': discount,
  'subtotal': '0.00',
  'total': '0.00',
  'items': items,
};

Map<String, dynamic> item({
  String id = 'item-1',
  String total = '10.00',
  String status = 'pending',
  String name = 'X-Burger',
}) => {
  'id': id,
  'product_name': name,
  'quantity': 1,
  'unit_price': total,
  'total_price': total,
  'status': status,
};

void main() {
  late Directory directory;
  late LocalOrderStore store;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-local-orders');
    store = LocalOrderStore(
      file: File('${directory.path}${Platform.pathSeparator}orders.sqlite'),
    );
  });

  tearDown(() async {
    await store.close();
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  test('guarda e devolve o pedido do servidor', () async {
    await store.saveFromServer(order(items: [item()]), scope: _scope);

    final stored = await store.read('order-1', scope: _scope);

    expect(stored, isNotNull);
    expect((stored!['items'] as List), hasLength(1));
  });

  test('pedido criado offline existe antes do primeiro item', () async {
    final local = await store.saveLocal(
      order(id: 'offline-order-1'),
      scope: _scope,
    );

    expect(local['updated_at'], isNotNull);
    expect(await store.read('offline-order-1', scope: _scope), isNotNull);
    final withItem = await store.addItem(
      'offline-order-1',
      item(id: 'offline-item-1'),
      scope: _scope,
    );
    expect((withItem!['items'] as List), hasLength(1));
  });

  test('pagamento offline é removido depois que o ID é reconciliado', () async {
    await store.saveLocal({
      ...order(),
      'offline_payments': [
        {
          'id': 'offline-payment-1',
          'amount': '10.00',
          '_offline_pending': true,
        },
      ],
    }, scope: _scope);

    await store.replaceId('offline-payment-1', 'payment-real-1', scope: _scope);
    final merged = await store.saveFromServer(order(), scope: _scope);

    expect(merged['offline_payments'], isNull);
  });

  test('a edição offline sobrevive a sair e voltar da tela', () async {
    await store.saveFromServer(order(items: [item()]), scope: _scope);

    await store.addItem(
      'order-1',
      item(id: 'offline-abc', total: '15.00', name: 'Suco'),
      scope: _scope,
    );

    // Releitura simulando o operador navegando e voltando ao pedido.
    final reread = await store.read('order-1', scope: _scope);

    expect((reread!['items'] as List), hasLength(2));
    expect(reread['subtotal'], '25.00');
    expect(reread['total'], '25.00');
  });

  test('os totais respeitam taxa e desconto do servidor', () async {
    await store.saveFromServer(
      order(serviceFee: '3.00', discount: '5.00'),
      scope: _scope,
    );

    final updated = await store.addItem(
      'order-1',
      item(total: '20.00'),
      scope: _scope,
    );

    // 20 + 3 de serviço - 5 de desconto. O terminal não recalcula a regra de
    // serviço nem a promoção; ele preserva o que o servidor definiu.
    expect(updated!['subtotal'], '20.00');
    expect(updated['total'], '18.00');
  });

  test('cancelar um item tira o valor do total sem apagar o registro', () async {
    await store.saveFromServer(
      order(
        items: [
          item(id: 'a', total: '10.00'),
          item(id: 'b', total: '4.00'),
        ],
      ),
      scope: _scope,
    );

    final updated = await store.voidItem('order-1', 'a', scope: _scope);

    expect(updated!['subtotal'], '4.00');
    // O item continua no pedido marcado como cancelado, como o servidor faria.
    final items = (updated['items'] as List).cast<Map<String, dynamic>>();
    expect(items, hasLength(2));
    expect(items.firstWhere((row) => row['id'] == 'a')['status'], 'voided');
  });

  test(
    'uma resposta do servidor não apaga o item que ainda está na fila',
    () async {
      await store.saveFromServer(
        order(items: [item(id: 'a')]),
        scope: _scope,
      );
      await store.addItem(
        'order-1',
        item(id: 'offline-novo', total: '7.00'),
        scope: _scope,
      );

      // O servidor responde sem conhecer o item da fila.
      final merged = await store.saveFromServer(
        order(items: [item(id: 'a')]),
        scope: _scope,
      );

      // Sumir aqui daria ao operador a impressão de que o lançamento se perdeu.
      final ids = (merged['items'] as List)
          .cast<Map<String, dynamic>>()
          .map((row) => '${row['id']}')
          .toList();
      expect(ids, containsAll(['a', 'offline-novo']));
    },
  );

  test('o item confirmado pelo servidor não vira duplicata', () async {
    await store.saveFromServer(order(), scope: _scope);
    await store.addItem(
      'order-1',
      item(id: 'offline-abc', total: '7.00'),
      scope: _scope,
    );

    // A fila sincronizou: o ID temporário virou o real.
    await store.replaceId('offline-abc', 'item-real', scope: _scope);
    final merged = await store.saveFromServer(
      order(
        items: [item(id: 'item-real', total: '7.00')],
      ),
      scope: _scope,
    );

    expect((merged['items'] as List), hasLength(1));
    expect((merged['items'] as List).single['id'], 'item-real');
  });

  test('a lista recente vem do mais novo para o mais antigo', () async {
    await store.saveFromServer(order(id: 'order-1'), scope: _scope);
    await Future<void>.delayed(const Duration(milliseconds: 5));
    await store.saveFromServer(order(id: 'order-2'), scope: _scope);

    final recent = await store.recent(scope: _scope);

    expect(recent.map((row) => row['id']), ['order-2', 'order-1']);
  });

  test('escopos diferentes não enxergam os pedidos um do outro', () async {
    await store.saveFromServer(order(), scope: _scope);

    expect(await store.read('order-1', scope: 'outra-conta'), isNull);
    expect(await store.recent(scope: 'outra-conta'), isEmpty);
  });

  test('mutação em pedido desconhecido não cria registro solto', () async {
    expect(await store.addItem('inexistente', item(), scope: _scope), isNull);
    expect(await store.recent(scope: _scope), isEmpty);
  });

  test('o total nunca fica negativo', () async {
    await store.saveFromServer(order(discount: '50.00'), scope: _scope);

    final updated = await store.addItem(
      'order-1',
      item(total: '10.00'),
      scope: _scope,
    );

    expect(updated!['total'], '0.00');
  });
}
