import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/data_signals.dart';

void main() {
  late DataSignals signals;

  setUp(() => signals = DataSignals());
  tearDown(() => signals.close());

  test('avisa quem observa o assunto', () async {
    final received = <String>[];
    signals.changes.listen(received.add);

    signals.emit('orders');
    await Future<void>.delayed(const Duration(milliseconds: 200));

    expect(received, ['orders']);
  });

  test('agrupa avisos próximos em um só', () async {
    var notifications = 0;
    signals.on('orders').listen((_) => notifications += 1);

    // Uma sincronização que atualiza vinte pedidos deve provocar uma
    // releitura, não vinte.
    for (var index = 0; index < 20; index++) {
      signals.emit('orders');
    }
    await Future<void>.delayed(const Duration(milliseconds: 200));

    expect(notifications, 1);
  });

  test('assuntos diferentes não se misturam', () async {
    final orders = <void>[];
    final menu = <void>[];
    signals.on('orders').listen(orders.add);
    signals.on('menu').listen(menu.add);

    signals.emit('orders');
    await Future<void>.delayed(const Duration(milliseconds: 200));

    expect(orders, hasLength(1));
    expect(menu, isEmpty);
  });

  test('avisos separados no tempo chegam separados', () async {
    var notifications = 0;
    signals.on('orders').listen((_) => notifications += 1);

    signals.emit('orders');
    await Future<void>.delayed(const Duration(milliseconds: 200));
    signals.emit('orders');
    await Future<void>.delayed(const Duration(milliseconds: 200));

    expect(notifications, 2);
  });

  group('assunto por rota', () {
    test('rotas observadas pelas telas', () {
      expect(DataSignals.topicFor('/orders/'), 'orders');
      expect(DataSignals.topicFor('/orders/abc-123/items/'), 'orders');
      expect(DataSignals.topicFor('/customers/'), 'customers');
      expect(DataSignals.topicFor('/menu/products/'), 'menu');
      expect(DataSignals.topicFor('/cash-register/current/'), 'cash');
    });

    test('rotas que ninguém observa não acordam a interface', () {
      // Não vale redesenhar a tela por um trabalho de impressão ou uma
      // leitura de balança.
      expect(DataSignals.topicFor('/print-jobs/'), isNull);
      expect(DataSignals.topicFor('/scales/abc/latest-reading/'), isNull);
      expect(DataSignals.topicFor('/auth/me/'), isNull);
    });
  });

  group('assuntos por evento WebSocket', () {
    test('cobre todos os recursos operacionais do PDV', () {
      expect(DataSignals.topicsForRealtimeResource('orders.orderitem'), {
        'orders',
      });
      expect(
        DataSignals.topicsForRealtimeResource('restaurants.command'),
        containsAll({'tables', 'orders'}),
      );
      expect(DataSignals.topicsForRealtimeResource('menu.product'), {'menu'});
      expect(DataSignals.topicsForRealtimeResource('customers.customer'), {
        'customers',
      });
      expect(DataSignals.topicsForRealtimeResource('payments.paymentmethod'), {
        'payments',
      });
      expect(DataSignals.topicsForRealtimeResource('printers.printer'), {
        'devices',
      });
      expect(DataSignals.topicsForRealtimeResource('printers.scale'), {
        'devices',
      });
    });

    test('leitura de balança não recarrega o cadastro de equipamentos', () {
      expect(DataSignals.topicsForRealtimeResource('printers.scalereading'), {
        'scale_readings',
      });
    });

    test('recurso novo usa reconciliação geral como fallback', () {
      expect(DataSignals.topicsForRealtimeResource('stock.stockmovement'), {
        'pdv',
      });
      expect(DataSignals.topicsForRealtimeResource(''), isEmpty);
    });
  });

  test('emitir depois de fechado não explode', () async {
    await signals.close();

    expect(() => signals.emit('orders'), returnsNormally);
  });
}
