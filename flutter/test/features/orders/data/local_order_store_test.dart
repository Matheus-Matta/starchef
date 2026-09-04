import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/formatters/value_formatters.dart';

import '../../../core/data/pdv_test_support.dart';

/// O pedido é o registro mais movimentado do PDV, e por isso o que mais dói
/// quando some. Estes testes garantem que a edição feita sem rede sobrevive a
/// sair e voltar da tela, que a versão do servidor não apaga o que ainda está
/// na fila, e que os totais batem com o que o operador vê.
///
/// Antes existia um segundo banco (`local_orders.sqlite`) só para isto; agora
/// é o mesmo `OrderRepository` que o resto do PDV usa (§1, §27).
void main() {
  late TestPdvStack stack;

  setUp(() async {
    stack = await TestPdvStack.create();
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
      {
        'id': 'prod-1',
        'name': 'Coxinha',
        'restaurant': 'rest-1',
        'current_price': '6.00',
      },
    ]);
  });

  tearDown(() async => stack.dispose());

  Future<String> abrirPedido() async {
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    return '${created.payload['id']}';
  }

  test('guarda e devolve o pedido do servidor', () async {
    await stack.gateway.orders.applyRemote({
      'id': 'pedido-1',
      'sequence': 7,
      'status': 'open',
      'items': const [],
    });

    final stored = await stack.gateway.orders.read('pedido-1');

    expect(stored!.payload['sequence'], 7);
  });

  test('pedido criado offline existe antes do primeiro item', () async {
    final orderId = await abrirPedido();

    final stored = await stack.gateway.orders.read(orderId);

    expect(stored, isNotNull);
    expect(stored!.payload['status'], 'open');
    expect(stored.payload['items'], isEmpty);
  });

  test('a edição offline sobrevive a sair e voltar da tela', () async {
    final orderId = await abrirPedido();
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 3},
    );

    // "Sair e voltar" é exatamente isto: uma leitura nova, sem estado de tela.
    final relido = await stack.gateway.read('/orders/$orderId/');

    expect((relido['items'] as List), hasLength(1));
    expect(ValueFormatters.number(relido['subtotal']), 18.0);
  });

  test('os totais respeitam taxa e desconto do servidor', () async {
    await stack.gateway.orders.applyRemote({
      'id': 'pedido-1',
      'status': 'open',
      'items': const [],
      'service_fee': '5.00',
      'discount': '2.00',
      'delivery_fee': '3.00',
    });
    await stack.gateway.write(
      'POST',
      '/orders/pedido-1/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );

    final stored = await stack.gateway.orders.read('pedido-1');

    // 6 (item) + 5 (serviço) + 3 (entrega) - 2 (desconto)
    expect(ValueFormatters.number(stored!.payload['total']), 12.0);
  });

  test('cancelar um item tira o valor do total sem apagar o registro', () async {
    final orderId = await abrirPedido();
    final added = await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );
    final itemId = '${(added.payload['_created_item'] as Map)['id']}';

    await stack.gateway.write(
      'DELETE',
      '/orders/$orderId/items/$itemId/void/',
      body: {'reason': 'Desistiu'},
    );

    final stored = await stack.gateway.orders.read(orderId);
    final items = (stored!.payload['items'] as List).cast<Map>();
    expect(items.single['status'], 'voided');
    expect(items.single['void_reason'], 'Desistiu');
    expect(ValueFormatters.number(stored.payload['total']), 0);
  });

  test('a versão do servidor não apaga o item que ainda está na fila', () async {
    final orderId = await abrirPedido();
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );

    // O servidor ainda não conhece o item lançado agora.
    await stack.gateway.orders.applyRemote({
      'id': orderId,
      'status': 'open',
      'items': const [],
    });

    final stored = await stack.gateway.orders.read(orderId);
    expect((stored!.payload['items'] as List), hasLength(1));
  });

  test('o item confirmado pelo servidor não vira duplicata', () async {
    await stack.gateway.orders.applyRemote({
      'id': 'pedido-1',
      'status': 'open',
      'items': [
        {'id': 'item-real', 'product': 'prod-1', 'total_price': '6.00'},
      ],
    });

    final stored = await stack.gateway.orders.read('pedido-1');

    expect((stored!.payload['items'] as List), hasLength(1));
  });

  test('a lista recente vem do mais novo para o mais antigo', () async {
    await stack.gateway.orders.applyRemote({
      'id': 'antigo',
      'sequence': 1,
      'created_at': '2026-01-01T10:00:00Z',
      'items': const [],
    });
    await stack.gateway.orders.applyRemote({
      'id': 'novo',
      'sequence': 2,
      'created_at': '2026-01-02T10:00:00Z',
      'items': const [],
    });

    final page = await stack.gateway.orders.list();

    expect(page.results.map((item) => item['id']), ['novo', 'antigo']);
  });

  test('escopos diferentes não enxergam os pedidos um do outro', () async {
    await stack.gateway.orders.applyRemote({
      'id': 'pedido-1',
      'items': const [],
    });

    stack.gateway.bindSession(scope: 'starchef.test|conta-2:operador-9');

    expect(await stack.gateway.orders.read('pedido-1'), isNull);
  });

  test('mutação em pedido desconhecido não cria registro solto', () async {
    await expectLater(
      stack.gateway.write(
        'POST',
        '/orders/nao-existe/items/',
        body: {'product': 'prod-1', 'quantity': 1},
      ),
      throwsA(isA<StateError>()),
    );

    expect(await stack.gateway.orders.read('nao-existe'), isNull);
  });

  test('o total nunca fica negativo', () async {
    await stack.gateway.orders.applyRemote({
      'id': 'pedido-1',
      'status': 'open',
      'items': const [],
      'discount': '999.00',
    });
    await stack.gateway.write(
      'POST',
      '/orders/pedido-1/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );

    final stored = await stack.gateway.orders.read('pedido-1');
    expect(ValueFormatters.number(stored!.payload['total']), 0);
  });

  test('pagamento offline some depois que o servidor confirma o pedido', () async {
    final orderId = await abrirPedido();
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/close/',
      body: {'service_fee_enabled': false},
    );
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/pay/',
      body: {'payment_method': 'pix', 'amount': '6.00'},
      context: {
        'payment_method': {'id': 'pix', 'method_type': 'pix'},
      },
    );
    final local = await stack.gateway.orders.payments(orderId);
    expect(local, hasLength(1));

    // Quando a fila sobe, o `OfflineFirstGateway` reconcilia o id do
    // recebimento antes de aplicar a resposta — é isso que impede o mesmo
    // pagamento de aparecer duas vezes.
    await stack.gateway.orders.replaceReference(
      orderId,
      '${local.single['id']}',
      'pagamento-real',
    );
    await stack.gateway.orders.applyRemote({
      'id': orderId,
      'status': 'paid',
      'items': const [],
      'payments': [
        {'id': 'pagamento-real', 'amount': '6.00'},
      ],
    }, overwriteLocalChanges: true);

    final payments = await stack.gateway.orders.payments(orderId);
    expect(payments, hasLength(1));
    expect(payments.single['id'], 'pagamento-real');
  });
}
