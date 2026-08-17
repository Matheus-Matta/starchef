import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/orders/presentation/order_presenter.dart';

void main() {
  test('completa pedido offline e calcula itens localmente', () {
    final order = OrderPresenter.completeOfflineOrder(
      {'id': 'offline-1', '_offline_pending': true},
      restaurantId: 'restaurant-1',
      type: 'table',
      table: {'id': 'table-1', 'number': '10'},
    );
    final first = OrderPresenter.offlineItem(
      response: {'id': 'offline-item-1', '_offline_pending': true},
      product: {'id': 'product-1', 'name': 'Pizza', 'current_price': '25.50'},
      quantity: 2,
    );
    final updated = OrderPresenter.withItems(order, [first]);

    expect(updated['status'], 'open');
    expect(updated['table_number'], '10');
    expect(updated['subtotal'], 51);
    expect(updated['total'], 51);
    expect((updated['items'] as List), hasLength(1));
  });

  test('pedido offline por comanda carrega qual comanda foi aberta', () {
    final order = OrderPresenter.completeOfflineOrder(
      {'id': 'offline-2', '_offline_pending': true},
      restaurantId: 'restaurant-1',
      type: 'command',
      command: {'id': 'command-1', 'number': 12, 'code': '0012'},
    );

    // Sem isso o cabeçalho do pedido aberto sem rede não sabe dizer qual
    // cartão está na mão do cliente — que é o único jeito de reencontrá-lo.
    expect(order['order_type'], 'command');
    expect(order['command'], 'command-1');
    expect(order['command_number'], 12);
    expect(order['command_code'], '0012');
  });

  test('item offline inclui variação e adicional no preço', () {
    final item = OrderPresenter.offlineItem(
      response: {
        'id': 'offline-item-2',
        '_offline_pending': true,
        'variations': ['variation-1'],
        'addons': ['addon-1'],
      },
      product: {
        'id': 'product-1',
        'name': 'Pizza',
        'current_price': '25.00',
        'variations': [
          {'id': 'variation-1', 'name': 'Grande', 'price_delta': '5.00'},
        ],
        'addons': [
          {'id': 'addon-1', 'name': 'Bacon', 'price': '3.50'},
        ],
      },
      quantity: 2,
    );

    expect(item['unit_price'], 33.5);
    expect(item['total_price'], 67);
    expect((item['variations'] as List).single['name'], 'Grande');
    expect((item['addons'] as List).single['addon_name'], 'Bacon');
  });

  test('fechamento offline calcula taxa e preserva o pedido completo', () {
    final closed = OrderPresenter.closeOfflineOrder(
      {
        'id': 'offline-order-1',
        'subtotal': '100.00',
        'discount': '5.00',
        'delivery_fee': '2.00',
        'items': const [],
      },
      serviceFeeEnabled: true,
      serviceFeePercent: 10,
    );

    expect(closed['id'], 'offline-order-1');
    expect(closed['service_fee'], '10.00');
    expect(closed['total'], '107.00');
    expect(closed['status'], 'awaiting_payment');
  });

  test('não modifica pedido confirmado pelo servidor', () {
    final online = {'id': 'server-1', 'status': 'awaiting_payment'};

    expect(
      identical(
        OrderPresenter.completeOfflineOrder(
          online,
          restaurantId: 'restaurant-1',
          type: 'counter',
        ),
        online,
      ),
      isTrue,
    );
  });
}
