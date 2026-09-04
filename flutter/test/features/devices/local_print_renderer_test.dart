import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/devices/domain/local_print_renderer.dart';

/// Os cupons montados no terminal precisam sair **iguais** aos do servidor: o
/// mesmo pedido impresso online e offline não pode gerar dois papéis
/// diferentes na mão do cliente. Este arquivo fixa o formato que espelha
/// `backend/apps/printers/services.py`.
void main() {
  final restaurant = {
    'trade_name': 'StarChef',
    'legal_name': 'StarChef Restaurante LTDA',
    'cnpj': '00.000.000/0001-00',
    'state_registration': '123456789',
    'address': 'Rua Principal, 100',
    'city': 'Sao Paulo',
    'state': 'SP',
    'zip_code': '01000-000',
    'phone': '(11) 90000-0000',
  };

  final order = {
    'id': 'pedido-1',
    'sequence': 42,
    'order_type': 'command',
    'command_code': 'CMD-7',
    'opened_at': '2026-08-28T13:05:00Z',
    'subtotal': '25.00',
    'service_fee': '2.50',
    'discount': '0.00',
    'delivery_fee': '0.00',
    'total': '27.50',
    'items': [
      {
        'id': 'item-1',
        'product_name': 'X-Burger',
        'quantity': 2,
        'unit_price': '10.00',
        'total_price': '20.00',
        'status': 'sent',
        'variations': const [],
        'addons': [
          {'addon_name': 'Bacon', 'total_price': '5.00'},
        ],
      },
      {
        'id': 'item-2',
        'product_name': 'Cancelado',
        'quantity': 1,
        'total_price': '99.00',
        'status': 'voided',
      },
    ],
  };

  test('recibo do cliente mantém o alinhamento de 42 colunas', () {
    final text = LocalPrintRenderer.customerReceipt(
      order: order,
      restaurant: restaurant,
      payments: [
        {
          'payment_method_name': 'Dinheiro',
          'amount': '30.00',
          'change_amount': '2.50',
        },
      ],
      operatorName: 'Ana',
    );
    final lines = text.split('\n');

    expect(lines.first.trim(), 'STARCHEF');
    expect(lines[1], contains('NAO E DOCUMENTO FISCAL'));
    expect(text, contains('CNPJ: 00.000.000/0001-00 - IE: 123456789'));
    expect(text, contains('Pedido nº 42'));
    expect(text, contains('Comanda: CMD-7'));
    expect(text, contains('Operador: Ana'));
    // Valor alinhado à direita, na mesma coluna do backend.
    expect(text, contains('2 x X-Burger'));
    final total = lines.firstWhere((line) => line.startsWith('TOTAL'));
    expect(total.length, LocalPrintRenderer.receiptWidth);
    expect(total.trimRight(), endsWith('R\$ 27.50'));
    // Item cancelado não entra no papel nem no que o cliente confere.
    expect(text, isNot(contains('Cancelado')));
    expect(text, contains('Troco'));
    expect(text, contains('CMD-7'));
  });

  test('recibo sem comanda não imprime código de barras', () {
    final text = LocalPrintRenderer.customerReceipt(
      order: {...order, 'order_type': 'counter', 'command_code': null},
      restaurant: restaurant,
      payments: const [],
    );

    expect(text, contains('BALCAO'));
    expect(text, isNot(contains('CODE128')));
  });

  test('delivery mostra o endereço em vez de "Mesa: - Comanda: -"', () {
    final lines = LocalPrintRenderer.orderContextLines({
      'order_type': 'delivery',
      'customer_name': 'Maria',
      'customer_phone': '(11) 91111-1111',
      'delivery_address': {
        'street': 'Rua das Flores',
        'number': '25',
        'complement': 'Apto 3',
        'district': 'Centro',
        'city': 'Sao Paulo',
        'state': 'SP',
        'reference': 'Portão azul',
      },
    });

    expect(lines.first, 'DELIVERY');
    expect(lines, contains('Cliente: Maria'));
    expect(lines, contains('Rua das Flores, 25 - Apto 3'));
    expect(lines, contains('Ref: Portão azul'));
  });

  test('cupom de cancelamento diz o que a cozinha precisa tirar da fila', () {
    final text = LocalPrintRenderer.cancellationTicket(
      order: order,
      item: {
        'product_name': 'X-Burger',
        'quantity': 2,
        'variations': const [],
        'addons': [
          {'addon_name': 'Bacon'},
        ],
      },
      reason: 'Cliente desistiu',
      operatorName: 'Ana',
    );

    expect(text, contains('CANCELAMENTO'));
    expect(text, contains('PEDIDO #42'));
    expect(text, contains('TIPO: COMANDA'));
    expect(text, contains('COMANDA: CMD-7'));
    expect(text, contains('CANCELAR 2x X-Burger'));
    expect(text, contains('  Bacon'));
    expect(text, contains('MOTIVO: Cliente desistiu'));
    expect(text, contains('SOLICITADO POR: Ana'));
    // Bobina de 58 mm: nenhuma linha pode estourar a largura.
    for (final line in text.split('\n')) {
      expect(line.length, lessThanOrEqualTo(LocalPrintRenderer.ticketWidth));
    }
  });

  test('nota de pesagem detalha o peso e o preço por quilo', () {
    final text = LocalPrintRenderer.weighTicket(
      order: {
        ...order,
        'items': [
          {
            'id': 'item-peso',
            'product_name': 'Buffet',
            'pricing_unit': 'kg',
            'quantity': 0.412,
            'unit_price': '59.90',
            'total_price': '24.68',
            'status': 'pending',
            'variations': const [],
          },
        ],
      },
      restaurant: restaurant,
    );

    expect(text, contains('NOTA DE PESAGEM'));
    expect(text, contains('Pedido #42  Comanda CMD-7'));
    // O peso sai com três casas, como a balança lê.
    expect(text, contains('0.412 kg x R\$ 59.90/kg'));
    expect(text, contains('TOTAL DO PEDIDO'));
    expect(text, contains('Pague no caixa'));
  });

  test('nota de teste identifica a impressora conferida', () {
    final text = LocalPrintRenderer.printerTest(
      printer: {
        'name': 'Cozinha',
        'driver_type': 'escpos',
        'connection_type': 'network',
        'host': '192.168.0.50',
        'port': 9100,
        'timeout_seconds': 10,
        'auto_print': true,
        'is_active': true,
      },
    );

    expect(text, contains('TESTE DE IMPRESSORA'));
    expect(text, contains('Nome: Cozinha'));
    expect(text, contains('IP: 192.168.0.50'));
    expect(text, contains('Impressao automatica: Ativada'));
    expect(text, contains('CONEXAO REALIZADA'));
  });

  test('produto por peso resolve tudo em uma linha só no recibo', () {
    // Repetir a quantidade numa segunda linha mostrava o mesmo peso duas
    // vezes no cupom.
    final text = LocalPrintRenderer.customerReceipt(
      order: {
        ...order,
        'items': [
          {
            'id': 'item-peso',
            'product_name': 'Buffet',
            'pricing_unit': 'kg',
            'quantity': 0.412,
            'unit_price': '59.90',
            'total_price': '24.68',
            'status': 'pending',
            'variations': const [],
          },
        ],
      },
      restaurant: restaurant,
      payments: const [],
    );

    expect(text, contains('0.412 x Buffet 59.90/kg'));
  });
}
