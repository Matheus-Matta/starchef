import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/local_id.dart';
import 'package:starchef_pdv/core/formatters/value_formatters.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';

import 'pdv_test_support.dart';

/// Dois defeitos que apareciam juntos no recebimento do PDV:
///
/// 1. o saldo do caixa não se mexia quando entrava (ou saía) dinheiro — a
///    conta local somava um `cash_sales_amount` que a API nunca enviou e
///    invertia o sinal de todo movimento que não fosse suprimento;
/// 2. remover um recebimento recém-lançado ia parar no servidor com o
///    identificador temporário e voltava "«offline-…» não é um UUID válido".
void main() {
  late TestPdvStack stack;

  setUp(() async {
    stack = await TestPdvStack.create();
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
      {
        'id': 'prod-1',
        'name': 'Pastel de queijo',
        'restaurant': 'rest-1',
        'current_price': '10.00',
        'pricing_unit': 'unit',
      },
    ]);
    await stack.gateway.repository(EntityCatalog.cashStation).applyRemoteList([
      {'id': 'caixa-1', 'name': 'Caixa 1', 'restaurant': 'rest-1'},
    ]);
  });

  tearDown(() async => stack.dispose());

  /// Caixa aberto com R$ 100 e um pedido fechado de R$ 20.
  Future<({String sessionId, String orderId})> openShift() async {
    final opened = await stack.gateway.write(
      'POST',
      '/cash-register/open/',
      body: {'cash_station': 'caixa-1', 'opening_amount': '100.00'},
      context: {
        'cash_station': {'id': 'caixa-1', 'name': 'Caixa 1'},
      },
    );
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    final orderId = '${created.payload['id']}';
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 2},
    );
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/close/',
      body: {'discount': 0, 'service_fee_enabled': false},
    );
    return (sessionId: '${opened.payload['id']}', orderId: orderId);
  }

  Future<Map<String, dynamic>> payCash(
    String orderId,
    String sessionId, {
    String amount = '20.00',
  }) async {
    final paid = await stack.gateway.write(
      'POST',
      '/orders/$orderId/pay/',
      body: {
        'payment_method': 'dinheiro',
        'amount': amount,
        'cash_register': sessionId,
      },
      context: {
        'payment_method': {'id': 'dinheiro', 'method_type': 'cash'},
      },
    );
    return paid.payload['_created_payment'] as Map<String, dynamic>;
  }

  double balanceOf(Map<String, dynamic> session) =>
      ValueFormatters.number(session['current_balance']);

  test('recebimento em dinheiro entra no saldo do caixa na hora', () async {
    final shift = await openShift();
    final before = await stack.gateway.read('/cash-register/current/');
    expect(balanceOf(before), 100.0);

    await payCash(shift.orderId, shift.sessionId);

    final after = await stack.gateway.read('/cash-register/current/');
    expect(balanceOf(after), 120.0);
    expect(ValueFormatters.number(after['expected_amount']), 120.0);
  });

  test('o troco não entra na gaveta — só o valor aplicado', () async {
    final shift = await openShift();

    final payment = await payCash(
      shift.orderId,
      shift.sessionId,
      amount: '50.00',
    );
    expect(payment['change_amount'], '30.00');

    final session = await stack.gateway.read('/cash-register/current/');
    expect(balanceOf(session), 120.0);
  });

  test('recebimento em cartão não mexe no dinheiro da gaveta', () async {
    final shift = await openShift();

    await stack.gateway.write(
      'POST',
      '/orders/${shift.orderId}/pay/',
      body: {'payment_method': 'debito', 'amount': '20.00'},
      context: {
        'payment_method': {'id': 'debito', 'method_type': 'card'},
      },
    );

    final session = await stack.gateway.read('/cash-register/current/');
    expect(balanceOf(session), 100.0);
  });

  test('remover um recebimento ainda na fila é operação local', () async {
    final shift = await openShift();
    final payment = await payCash(shift.orderId, shift.sessionId);
    final paymentId = '${payment['id']}';
    expect(LocalId.isTemporary(paymentId), isTrue);

    // A rota não pode sair deste terminal: o servidor não conhece este id.
    final path = '/orders/${shift.orderId}/payments/$paymentId/';
    expect(stack.gateway.handlesWrite('DELETE', path, null), isTrue);

    final result = await stack.gateway.write('DELETE', path);

    expect(result.payload['payment_status'], 'pending');
    expect(result.payload['status'], 'awaiting_payment');
    expect((result.payload['offline_payments'] as List), isEmpty);
  });

  test('remover o recebimento tira a cobrança da fila', () async {
    final shift = await openShift();
    final payment = await payCash(shift.orderId, shift.sessionId);
    final paymentId = '${payment['id']}';

    await stack.gateway.write(
      'DELETE',
      '/orders/${shift.orderId}/payments/$paymentId/',
    );

    // Deixar o `pay` na fila faria o servidor registrar depois um dinheiro
    // que o operador já apagou aqui.
    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(
      queued.map((entry) => entry.path),
      isNot(contains('/orders/${shift.orderId}/pay/')),
    );
  });

  test('remover o recebimento em dinheiro devolve o saldo do caixa', () async {
    final shift = await openShift();
    final payment = await payCash(shift.orderId, shift.sessionId);

    await stack.gateway.write(
      'DELETE',
      '/orders/${shift.orderId}/payments/${payment['id']}/',
    );

    final session = await stack.gateway.read('/cash-register/current/');
    expect(balanceOf(session), 100.0);
  });

  test('recebimento com id definitivo continua sendo do servidor', () async {
    final shift = await openShift();
    // Um pagamento já sincronizado tem id de verdade: cancelar envolve reabrir
    // mesa/comanda e estornar estoque, e isso é decisão do servidor.
    final path =
        '/orders/${shift.orderId}/payments/3f1a2b4c-0000-4000-8000-000000000001/';

    expect(stack.gateway.handlesWrite('DELETE', path, null), isFalse);
  });

  test('recebimento em entrega não é apagado por baixo do pano', () async {
    final shift = await openShift();
    final payment = await payCash(shift.orderId, shift.sessionId);
    // Simula a fila já tendo reservado a operação para envio.
    await stack.database.execute(
      "UPDATE sync_queue SET status = 'PROCESSING' WHERE path = ?",
      ['/orders/${shift.orderId}/pay/'],
    );

    expect(
      () => stack.gateway.write(
        'DELETE',
        '/orders/${shift.orderId}/payments/${payment['id']}/',
      ),
      throwsA(isA<ApiException>()),
    );
  });

  test('a cópia do servidor não apaga o que ainda está na fila', () async {
    final shift = await openShift();
    await payCash(shift.orderId, shift.sessionId);

    // Chega a sessão do servidor confirmando a abertura e uma sangria — mas
    // ele ainda não sabe do recebimento que está na fila. Duas coisas se
    // provam aqui: a sangria já vem negativa de lá e não pode ser invertida
    // de novo, e o recebimento pendente não pode sumir da tela (era o saldo
    // voltando atrás sozinho depois de receber em dinheiro).
    await stack.gateway.repository(EntityCatalog.cashSession).applyRemote({
      'id': shift.sessionId,
      'restaurant': 'rest-1',
      'status': 'open',
      'opening_amount': '100.00',
      'current_balance': '70.00',
      'movements': [
        {
          'id': 'mov-abertura',
          'movement_type': 'opening',
          'amount': '100.00',
          'status': 'approved',
        },
        {
          'id': 'mov-sangria',
          'movement_type': 'withdrawal',
          'amount': '-30.00',
          'status': 'approved',
        },
      ],
      'updated_at': DateTime.now().toUtc().toIso8601String(),
    }, overwriteLocalChanges: true);

    final session = await stack.gateway.read('/cash-register/current/');
    expect(balanceOf(session), 90.0);
    expect(ValueFormatters.number(session['expected_amount']), 90.0);
  });

  test('o movimento do servidor substitui o lançamento local ao subir', () async {
    final shift = await openShift();
    final payment = await payCash(shift.orderId, shift.sessionId);
    final sessions = stack.gateway.repository(EntityCatalog.cashSession);

    // A entrega do `pay` troca o id temporário do pagamento pelo definitivo,
    // aqui e na gaveta. É o que faz o lançamento local deixar de ser
    // preservado quando o movimento de verdade chega.
    await sessions.replaceReference(
      shift.sessionId,
      '${payment['id']}',
      'pag-real-1',
    );
    await sessions.applyRemote({
      'id': shift.sessionId,
      'restaurant': 'rest-1',
      'status': 'open',
      'opening_amount': '100.00',
      'current_balance': '120.00',
      'movements': [
        {
          'id': 'mov-abertura',
          'movement_type': 'opening',
          'amount': '100.00',
          'status': 'approved',
        },
        {
          'id': 'mov-venda',
          'payment': 'pag-real-1',
          'movement_type': 'sale',
          'amount': '20.00',
          'status': 'approved',
        },
      ],
      'updated_at': DateTime.now().toUtc().toIso8601String(),
    }, overwriteLocalChanges: true);

    final session = await stack.gateway.read('/cash-register/current/');
    final movements = (session['movements'] as List).cast<Map>();
    // Só o movimento do servidor sobra: manter também o lançamento local
    // somaria o mesmo dinheiro duas vezes.
    expect(movements.map((movement) => '${movement['id']}'), [
      'mov-abertura',
      'mov-venda',
    ]);
    expect(balanceOf(session), 120.0);
  });
}
