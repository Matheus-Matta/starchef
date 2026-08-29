import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/local_id.dart';
import 'package:starchef_pdv/core/formatters/value_formatters.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';

import 'pdv_test_support.dart';

/// A regra fundamental (§30): com a internet desligada, o restaurante inteiro
/// continua operando. Estes testes percorrem o caminho de um turno — abrir
/// caixa, abrir pedido, lançar item, fechar, receber, sangrar, fechar caixa —
/// sem que nenhuma linha de rede seja executada.
void main() {
  late TestPdvStack stack;

  setUp(() async {
    stack = await TestPdvStack.create();
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
      {
        'id': 'prod-1',
        'name': 'Pastel de queijo',
        'restaurant': 'rest-1',
        'current_price': '7.50',
        'pricing_unit': 'unit',
      },
      {
        'id': 'prod-2',
        'name': 'Buffet por quilo',
        'restaurant': 'rest-1',
        'current_price': '59.90',
        'pricing_unit': 'kg',
      },
    ]);
    await stack.gateway.repository(EntityCatalog.cashStation).applyRemoteList([
      {'id': 'caixa-1', 'name': 'Caixa 1', 'restaurant': 'rest-1'},
    ]);
  });

  tearDown(() async => stack.dispose());

  test('leitura de coleção responde do SQLite, paginada (§3, §13)', () async {
    final page = await stack.gateway.read(
      '/menu/products/',
      query: {'page': 1, 'page_size': 20, 'restaurant': 'rest-1'},
    );

    expect(page['count'], 2);
    expect((page['results'] as List), hasLength(2));
    expect(page['_local'], isTrue);
  });

  test('leitura de um registro inexistente é sinalizada, não inventada', () async {
    final response = await stack.gateway.read('/menu/products/nao-existe/');

    expect(response['_empty'], isTrue);
  });

  test('venda completa sem rede: pedido, item, fechamento e pagamento', () async {
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    final orderId = '${created.payload['id']}';
    expect(LocalId.isTemporary(orderId), isTrue);

    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 2},
    );
    final withItem = await stack.gateway.read('/orders/$orderId/');
    expect((withItem['items'] as List), hasLength(1));
    expect(ValueFormatters.number(withItem['subtotal']), 15.0);

    stack.gateway.serviceFeePercent = 10;
    final closed = await stack.gateway.write(
      'POST',
      '/orders/$orderId/close/',
      body: {'discount': 0, 'service_fee_enabled': true},
    );
    expect(closed.payload['status'], 'awaiting_payment');
    expect(ValueFormatters.number(closed.payload['total']), 16.5);

    final paid = await stack.gateway.write(
      'POST',
      '/orders/$orderId/pay/',
      body: {'payment_method': 'dinheiro', 'amount': '20.00'},
      context: {
        'payment_method': {'id': 'dinheiro', 'method_type': 'cash'},
      },
    );
    expect(paid.payload['payment_status'], 'paid');
    final payment = paid.payload['_created_payment'] as Map<String, dynamic>;
    // Recebeu 20, devia 16,50: o troco não entra no caixa como venda.
    expect(payment['amount'], '16.50');
    expect(payment['change_amount'], '3.50');
  });

  test('cancelar item recalcula o total sem apagar a linha', () async {
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    final orderId = '${created.payload['id']}';
    final added = await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );
    final itemId = '${(added.payload['_created_item'] as Map)['id']}';

    final voided = await stack.gateway.write(
      'DELETE',
      '/orders/$orderId/items/$itemId/void/',
      body: {'reason': 'Cliente desistiu'},
    );

    final items = (voided.payload['items'] as List).cast<Map>();
    expect(items.single['status'], 'voided');
    expect(ValueFormatters.number(voided.payload['subtotal']), 0);
  });

  test('produto vendido a peso entra no pedido sem rede (§30)', () async {
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    final orderId = '${created.payload['id']}';

    // O peso é um valor, não um registro do servidor: pode viajar depois.
    expect(
      stack.gateway.handlesWrite('POST', '/orders/$orderId/items/', {
        'product': 'prod-2',
        'weight_kg': '0.400',
      }),
      isTrue,
    );
    // Já a leitura física da balança é um registro criado no instante da
    // pesagem — reenviá-la mais tarde não faria sentido.
    expect(
      stack.gateway.handlesWrite('POST', '/orders/$orderId/items/', {
        'product': 'prod-2',
        'scale_reading': 'leitura-1',
      }),
      isFalse,
    );

    final added = await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-2', 'weight_kg': '0.400'},
    );
    final item = added.payload['_created_item'] as Map<String, dynamic>;
    expect(item['quantity'], 0.4);
    expect(ValueFormatters.number(item['total_price']), closeTo(23.96, 0.001));
  });

  test('troco considera o que o servidor já confirmou (§7)', () async {
    // Meia venda paga online, metade offline. Olhando só a fila, o troco era
    // calculado sobre o valor cheio e devolvia dinheiro a mais ao cliente.
    await stack.gateway.orders.applyRemote({
      'id': 'pedido-1',
      'status': 'awaiting_payment',
      'total': '100.00',
      'items': const [],
      'payments': [
        {'id': 'pagamento-real', 'amount': '60.00'},
      ],
    });

    final paid = await stack.gateway.write(
      'POST',
      '/orders/pedido-1/pay/',
      body: {'payment_method': 'dinheiro', 'amount': '50.00'},
      context: {
        'payment_method': {'id': 'dinheiro', 'method_type': 'cash'},
      },
    );

    final payment = paid.payload['_created_payment'] as Map<String, dynamic>;
    // Faltavam 40; recebeu 50; troco 10.
    expect(payment['amount'], '40.00');
    expect(payment['change_amount'], '10.00');
    expect(paid.payload['payment_status'], 'paid');
  });

  test('pedido do garçom nasce com o primeiro item (§9)', () async {
    // `/orders/create-with-item/` é o caminho do app do garçom: criar só o
    // pedido deixaria uma comanda vazia logo depois de escolher o produto.
    final created = await stack.gateway.write(
      'POST',
      '/orders/create-with-item/',
      body: {
        'order_type': 'counter',
        'item': {'product': 'prod-1', 'quantity': 2},
      },
    );

    final items = (created.payload['items'] as List).cast<Map>();
    expect(items, hasLength(1));
    expect(items.single['product_name'], 'Pastel de queijo');
    expect(ValueFormatters.number(created.payload['subtotal']), 15.0);
  });

  test('turno de caixa inteiro funciona offline (§30)', () async {
    final opened = await stack.gateway.write(
      'POST',
      '/cash-register/open/',
      body: {'cash_station': 'caixa-1', 'opening_amount': '150.00'},
      context: {
        'cash_station': {'id': 'caixa-1', 'name': 'Caixa 1'},
        'operator_name': 'Ana',
      },
    );
    final sessionId = '${opened.payload['id']}';
    expect(opened.payload['status'], 'open');

    final current = await stack.gateway.read('/cash-register/current/');
    expect(current['id'], sessionId);

    await stack.gateway.write(
      'POST',
      '/cash-register/$sessionId/withdrawal/',
      body: {'amount': '50.00', 'reason': 'Sangria do turno'},
    );
    final afterSupply = await stack.gateway.write(
      'POST',
      '/cash-register/$sessionId/supply/',
      body: {'amount': '20.00', 'reason': 'Troco'},
    );
    expect(
      ValueFormatters.number(afterSupply.payload['expected_amount']),
      120.0,
    );

    final closed = await stack.gateway.write(
      'POST',
      '/cash-register/$sessionId/close/',
      body: {'actual_amount': '120.00'},
    );
    expect(closed.payload['status'], 'closed');
    expect(ValueFormatters.number(closed.payload['difference_amount']), 0);

    // Nenhuma dessas operações se perdeu: todas estão na fila para subir.
    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(queued.map((entry) => entry.path), [
      '/cash-register/open/',
      '/cash-register/$sessionId/withdrawal/',
      '/cash-register/$sessionId/supply/',
      '/cash-register/$sessionId/close/',
    ]);
  });

  test('pesagem fecha na comanda sem servidor (§30)', () async {
    // A leitura do peso é local (porta serial). O que dependia da API era
    // transformar a leitura em item: sem isso, o buffet pesava e ninguém
    // conseguia cobrar.
    stack.gateway.connectivity = () => false;
    await stack.gateway.repository(EntityCatalog.command).applyRemote({
      'id': 'comanda-1',
      'code': 'CMD-7',
      'number': 7,
      'restaurant': 'rest-1',
    });

    final result = await stack.gateway.write(
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

    final items = (result.payload['items'] as List).cast<Map>();
    expect(items, hasLength(2));
    expect(items.first['product_name'], 'Buffet por quilo');
    expect(items.first['quantity'], 0.4);
    expect(items.last['product_name'], 'Pastel de queijo');
    // 0,400 × 59,90 + 7,50
    expect(
      ValueFormatters.number(result.payload['subtotal']),
      closeTo(31.46, 0.001),
    );

    // UMA operação na fila, não uma por item: o servidor executa o
    // `checkout-command` inteiro de novo, e lançar cada item também
    // duplicaria tudo no replay.
    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(queued, hasLength(1));
    expect(queued.single.path, '/scales/balanca-1/checkout-command/');
    // Sem `ScaleReading` (criá-la exige servidor), o peso bruto acompanha a
    // operação e o backend materializa a leitura no replay.
    expect(queued.single.payload!['weight_kg'], '0.400');
    expect(queued.single.payload!['command_code'], 'CMD-7');
  });

  test('pesagem com comanda desconhecida falha com o motivo', () async {
    stack.gateway.connectivity = () => false;

    await expectLater(
      stack.gateway.write(
        'POST',
        '/scales/balanca-1/checkout-command/',
        body: {'command_code': 'CMD-404', 'weight_kg': '0.400'},
        context: {
          'weighed_product': {'id': 'prod-2', 'current_price': '10.00'},
        },
      ),
      throwsA(isA<ApiException>()),
    );
  });

  test('autorização do caixa aplicada sem servidor (§30)', () async {
    // Um caixa que fecha com diferença ficava travado até a internet voltar,
    // com o operador impedido de encerrar o turno.
    stack.gateway.connectivity = () => false;
    await stack.gateway.repository(EntityCatalog.cashSession).applyRemote({
      'id': 'sessao-1',
      'restaurant': 'rest-1',
      'status': 'pending_manager_approval',
      'opening_amount': '100.00',
    });

    final approved = await stack.gateway.write(
      'POST',
      '/cash-register/sessao-1/approve/',
      body: {
        'reason': 'Diferença conferida.',
        'cash_password_proof': 'prova-hmac',
        'proof_nonce': 'nonce-1',
      },
      context: {'approver_name': 'Ana'},
    );

    // O mesmo nome que o backend usa: enquanto as duas grafias divergiam, um
    // caixa ja fechado continuava "nao finalizado" para este terminal.
    expect(approved.payload['status'], 'closed_with_difference');
    expect(approved.payload['approved_by_name'], 'Ana');
    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    // A senha em texto nunca entra na fila: só a prova de que o terminal
    // conhece o hash.
    expect(queued.single.payload!.containsKey('cash_password'), isFalse);
    expect(queued.single.payload!['cash_password_proof'], 'prova-hmac');
  });

  test('emissão fiscal vai para a fila própria e não trava a venda (§16)', () async {
    final result = await stack.gateway.write(
      'POST',
      '/invoices/emit/',
      body: {'order': 'pedido-1', 'cpf': '00000000000'},
    );

    expect(result.payload['_fiscal_pending'], isTrue);
    expect(result.payload['fiscal_status'], 'PENDING');
    final pending = await stack.fiscalQueue.documents(
      scope: TestPdvStack.scope,
    );
    expect(pending.single.orderId, 'pedido-1');
    expect(
      await stack.fiscalQueue.statusForOrder(
        scope: TestPdvStack.scope,
        orderId: 'pedido-1',
      ),
      FiscalStatus.pending,
    );
    // A emissão não entra na fila de vendas: uma nota recusada pela SEFAZ não
    // pode segurar a sincronização dos pedidos.
    expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
  });

  test('impressão do DANFE continua exigindo servidor', () async {
    // `/invoices/<id>/print/` contém `/print/`: renderizar o documento é
    // trabalho do backend, e sem nota autorizada não há o que imprimir.
    expect(
      stack.gateway.handlesWrite('POST', '/invoices/nota-1/print/', const {}),
      isFalse,
    );
    expect(
      stack.gateway.handlesWrite('POST', '/invoices/emit/', const {}),
      isTrue,
    );
  });

  test('rotas que exigem servidor de verdade não são atendidas localmente', () async {
    for (final path in const [
      '/auth/login/',
      '/print-jobs/',
      '/scales/readings/',
      '/printers/templates/',
      '/reports/sales/',
    ]) {
      expect(
        stack.gateway.handlesWrite('POST', path, const {}),
        isFalse,
        reason: path,
      );
    }
  });

  test('pesagem e autorização preferem o servidor quando ele responde', () async {
    // Online, é o servidor que liga a leitura ao item e que sabe validar o
    // login de um gerente. Interceptar sempre degradaria o fluxo normal só
    // para atender o caso da rede caída.
    stack.gateway.connectivity = () => true;
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/scales/balanca-1/checkout-command/',
        const {},
      ),
      isFalse,
    );
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/cash-register/sessao-1/approve/',
        const {},
      ),
      isFalse,
    );

    // Sem servidor, o terminal assume as duas — senão o buffet para de pesar
    // e um caixa com diferença não fecha o turno.
    stack.gateway.connectivity = () => false;
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/scales/balanca-1/checkout-command/',
        const {},
      ),
      isTrue,
    );
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/cash-register/sessao-1/approve/',
        const {},
      ),
      isTrue,
    );
  });

  test('ação desconhecida sobre o recurso vai para o servidor', () async {
    // `DELETE /orders/<id>/payments/<id>/` é um estorno, não uma exclusão do
    // pedido. Sem esta guarda ele caía no caminho genérico de escrita e
    // marcava o PEDIDO INTEIRO como excluído.
    expect(
      stack.gateway.handlesWrite(
        'DELETE',
        '/orders/pedido-1/payments/pag-1/',
        const {},
      ),
      isFalse,
    );
    expect(
      stack.gateway.handlesWrite('POST', '/orders/pedido-1/close/', const {}),
      isTrue,
    );
    expect(
      stack.gateway.handlesWrite(
        'DELETE',
        '/orders/pedido-1/items/item-1/void/',
        const {},
      ),
      isTrue,
    );
  });

  test('modelos de impressão não passam pelo roteador de entidades', () async {
    // `/printers/templates/` devolve `{"templates": [...]}` sem id: tratá-lo
    // como coleção de entidades deixaria o agente de impressão sem modelo.
    expect(stack.gateway.handlesRead('/printers/templates/'), isFalse);
    expect(stack.gateway.handlesRead('/printers/'), isTrue);
  });

  test('vincular a mesa da comanda funciona sem rede (§30)', () async {
    await stack.gateway.repository(EntityCatalog.command).applyRemote({
      'id': 'comanda-1',
      'number': 12,
      'restaurant': 'rest-1',
      'status': 'free',
    });

    final linked = await stack.gateway.write(
      'POST',
      '/commands/comanda-1/link-table/',
      body: {'table_id': 'mesa-3'},
    );

    expect(linked.payload['current_table'], 'mesa-3');
    final unlinked = await stack.gateway.write(
      'POST',
      '/commands/comanda-1/unlink-table/',
      body: const {},
    );
    expect(unlinked.payload['current_table'], isNull);
  });

  test('sem sessão vinculada o gateway não atende nada', () async {
    stack.gateway.clearSession();

    expect(stack.gateway.handlesRead('/orders/'), isFalse);
    expect(stack.gateway.handlesWrite('POST', '/orders/', const {}), isFalse);
  });

  test('diagnóstico resume fila, fila fiscal e o que existe no banco', () async {
    await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    await stack.gateway.write(
      'POST',
      '/invoices/emit/',
      body: {'order': 'pedido-1'},
    );

    final diagnostics = await stack.gateway.diagnostics();

    expect(diagnostics['bound'], isTrue);
    expect((diagnostics['queue'] as Map)['pending'], 1);
    expect(diagnostics['fiscal_pending'], 1);
    expect((diagnostics['entities'] as Map)[EntityCatalog.product], 2);
  });
}
