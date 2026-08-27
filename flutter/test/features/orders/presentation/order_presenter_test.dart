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

  group('buildOfflineKitchenTickets', () {
    final products = [
      {'id': 'product-1', 'name': 'X-Burger', 'sector': 'sector-1'},
      {'id': 'product-2', 'name': 'Refrigerante', 'sector': null},
    ];

    test('ignora item cujo produto não tem setor', () {
      final tickets = OrderPresenter.buildOfflineKitchenTickets(
        order: const {'sequence': 9, 'order_type': 'table'},
        table: null,
        command: null,
        pendingItems: [
          {'product': 'product-2', 'product_name': 'Refrigerante', 'quantity': 1},
        ],
        products: products,
        printers: [
          {'id': 'printer-1', 'sector': 'sector-1', 'is_active': true},
        ],
        batchSerial: 'batch-serial-1',
      );

      expect(tickets, isEmpty);
    });

    test('setor sem impressora ativa não gera ticket', () {
      final tickets = OrderPresenter.buildOfflineKitchenTickets(
        order: const {'sequence': 9, 'order_type': 'table'},
        table: null,
        command: null,
        pendingItems: [
          {'product': 'product-1', 'product_name': 'X-Burger', 'quantity': 1},
        ],
        products: products,
        printers: [
          {'id': 'printer-1', 'sector': 'sector-1', 'is_active': false},
        ],
        batchSerial: 'batch-serial-1',
      );

      expect(tickets, isEmpty);
    });

    test('duas impressoras no mesmo setor recebem o mesmo texto', () {
      final tickets = OrderPresenter.buildOfflineKitchenTickets(
        order: const {'sequence': 9, 'order_type': 'table'},
        table: {'number': '7'},
        command: null,
        pendingItems: [
          {'product': 'product-1', 'product_name': 'X-Burger', 'quantity': 2},
        ],
        products: products,
        printers: [
          {'id': 'printer-1', 'sector': 'sector-1', 'is_active': true},
          {'id': 'printer-2', 'sector': 'sector-1', 'is_active': true},
        ],
        batchSerial: 'batch-serial-1',
      );

      expect(tickets, hasLength(2));
      expect(tickets[0].text, tickets[1].text);
      expect(
        tickets.map((ticket) => ticket.printer['id']),
        containsAll(['printer-1', 'printer-2']),
      );
    });

    test(
      'texto traz mesa/comanda, variações, adicionais, observação e REF',
      () {
        final tickets = OrderPresenter.buildOfflineKitchenTickets(
          order: const {'sequence': 9, 'order_type': 'table'},
          table: {'number': '7'},
          command: {'code': '0012'},
          pendingItems: [
            {
              'product': 'product-1',
              'product_name': 'X-Burger',
              'quantity': 1.5,
              'variations': [
                {'name': 'Grande'},
              ],
              'addons': [
                {'addon_name': 'Bacon', 'quantity': 2},
              ],
              'customer_note': 'Sem cebola',
            },
          ],
          products: products,
          printers: [
            {'id': 'printer-1', 'sector': 'sector-1', 'is_active': true},
          ],
          batchSerial: 'batch-serial-1',
        );

        final text = tickets.single.text;
        final mesaLine = text.indexOf('MESA: 7');
        final comandaLine = text.indexOf('COMANDA: 0012');
        final itemLine = text.indexOf('1.5x X-Burger');
        final variationLine = text.indexOf('VAR: Grande');
        final addonLine = text.indexOf('+ 2x Bacon');
        final noteLine = text.indexOf('OBS: Sem cebola');
        final refLine = text.indexOf('REF: batch-serial-1');

        expect(mesaLine, greaterThanOrEqualTo(0));
        expect(comandaLine, greaterThan(mesaLine));
        expect(itemLine, greaterThan(comandaLine));
        expect(variationLine, greaterThan(itemLine));
        expect(addonLine, greaterThan(variationLine));
        expect(noteLine, greaterThan(addonLine));
        expect(refLine, greaterThan(noteLine));
      },
    );

    test('cabeçalho identifica pedido, setor, atendente e total de itens', () {
      final tickets = OrderPresenter.buildOfflineKitchenTickets(
        order: const {
          'sequence': 45,
          'order_type': 'delivery',
          'customer_name': 'Joao',
        },
        table: null,
        command: null,
        pendingItems: [
          {'product': 'product-1', 'product_name': 'X-Burger', 'quantity': 2},
          {'product': 'product-1', 'product_name': 'X-Burger', 'quantity': 1},
        ],
        products: products,
        printers: [
          {
            'id': 'printer-1',
            'sector': 'sector-1',
            'sector_name': 'Cozinha',
            'is_active': true,
          },
        ],
        batchSerial: 'batch-serial-1',
        operatorName: 'Maria',
        now: DateTime(2026, 8, 27, 20, 30, 15),
      );

      final text = tickets.single.text;
      expect(text, contains('COZINHA'));
      expect(text, contains('PEDIDO #45'));
      expect(text, contains('27/08/2026 20:30:15'));
      // Entrega precisa estar explícita: sem mesa nem comanda, a cozinha não
      // teria como saber que o pedido não é do salão.
      expect(text, contains('DELIVERY'));
      expect(text, contains('CLIENTE: Joao'));
      expect(text, contains('ATENDENTE: Maria'));
      expect(text, contains('TOTAL DE ITENS'));
      expect(text, contains('3'));
    });
  });

  test('generateBatchSerial gera um UUID v4 novo a cada chamada', () {
    final first = OrderPresenter.generateBatchSerial();
    final second = OrderPresenter.generateBatchSerial();
    final uuidV4 = RegExp(
      r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    );

    expect(first, isNot(equals(second)));
    expect(uuidV4.hasMatch(first), isTrue);
    expect(uuidV4.hasMatch(second), isTrue);
  });
}
