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

  test('pedido que ja subiu continua respondendo pelo id antigo', () async {
    // A tela pega o id no momento em que o pedido nasce. Quando a criação sobe,
    // o registro passa a viver sob o id do SERVIDOR e o temporário some do
    // armazenamento — mas a tela continua com ele em mãos. Era assim que um
    // pedido recém-aberto pela comanda recusava o primeiro item com "Pedido
    // offline-… não existe no armazenamento local", e só voltava a funcionar
    // quando o operador saía e entrava de novo.
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'command'},
    );
    final temporaryId = '${created.payload['id']}';
    expect(LocalId.isTemporary(temporaryId), isTrue);

    const remoteId = '3f1a2b4c-0000-4000-8000-0000000000aa';
    await stack.gateway
        .repository(EntityCatalog.order)
        .replaceId(temporaryId, remoteId);

    // O id antigo já não existe como registro; só no mapa de IDs.
    final added = await stack.gateway.write(
      'POST',
      '/orders/$temporaryId/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );

    expect('${added.payload['id']}', remoteId);
    expect((added.payload['items'] as List), hasLength(1));

    // E a leitura pelo id antigo devolve o pedido de verdade, não um vazio.
    final read = await stack.gateway.read('/orders/$temporaryId/');
    expect('${read['id']}', remoteId);
    expect((read['items'] as List), hasLength(1));
  });

  test('pedido que nunca subiu e descartado sem virar requisição', () async {
    // Abrir uma comanda e sair sem lançar nada nao pode deixar rastro. Hoje
    // isso e ainda mais direto: sem item, o pedido nem chega a virar operação
    // — ele é um rascunho deste terminal. O descarte continua existindo para o
    // caso de já haver algo enfileirado (um item lançado e removido em
    // seguida, por exemplo).
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'command'},
    );
    final orderId = '${created.payload['id']}';
    expect(LocalId.isTemporary(orderId), isTrue);
    expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);

    final path = '/orders/$orderId/cancel/';
    // A rota não sai do terminal: o servidor não conhece este pedido.
    expect(stack.gateway.handlesWrite('POST', path, const {}), isTrue);

    final result = await stack.gateway.write('POST', path);

    expect(result.payload['_discarded'], isTrue);
    // Nada na fila: a criação sai junto, senão o pedido voltaria na próxima
    // sincronização.
    expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
    // E nada no armazenamento: a comanda volta a ficar livre aqui.
    expect(await stack.gateway.orders.read(orderId), isNull);
  });

  test('rascunhos orfaos sao varridos; o aberto e os com item ficam', () async {
    // Comanda aberta e abandonada sem passar pela saida da tela (app fechado,
    // tela que caiu) deixava um `#LOCAL-…` de R$ 0,00 na lista de Pedidos — e
    // como rascunho nao ocupa a comanda, reabri-la criava mais um.
    Future<String> draft() async {
      final created = await stack.gateway.write(
        'POST',
        '/orders/',
        body: {'restaurant': 'rest-1', 'order_type': 'command'},
      );
      return '${created.payload['id']}';
    }

    final orphan1 = await draft();
    final orphan2 = await draft();
    final open = await draft();
    final withItem = await draft();
    await stack.gateway.write(
      'POST',
      '/orders/$withItem/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );
    final promoted = await stack.gateway.read('/orders/$withItem/');
    final promotedId = '${promoted['id']}';

    final removed = await stack.gateway.discardStaleDrafts(except: open);

    expect(removed, 2);
    expect(await stack.gateway.orders.read(orphan1), isNull);
    expect(await stack.gateway.orders.read(orphan2), isNull);
    expect(await stack.gateway.orders.read(open), isNotNull);
    expect(await stack.gateway.orders.read(promotedId), isNotNull);
    // Segunda passada nao tem o que fazer.
    expect(await stack.gateway.discardStaleDrafts(except: open), 0);
  });

  test('pedido com id do servidor continua sendo cancelado por ele', () async {
    // Cancelar o que o servidor conhece envolve senha, motivo, liberação de
    // mesa e estorno — nada disso se resolve aqui.
    const path = '/orders/3f1a2b4c-0000-4000-8000-0000000000bb/cancel/';

    expect(stack.gateway.handlesWrite('POST', path, const {}), isFalse);
  });

  test('pedido em entrega não é descartado por baixo do pano', () async {
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'command'},
    );
    final orderId = '${created.payload['id']}';
    // Com o primeiro item o pedido deixa de ser rascunho e vira operação na
    // fila — que é o que pode estar em entrega neste instante.
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );
    // A fila já reservou a operação: o servidor pode estar gravando a venda
    // neste instante.
    await stack.database.execute(
      "UPDATE sync_queue SET status = 'PROCESSING' WHERE entity_id = ?",
      [orderId],
    );

    expect(
      () => stack.gateway.write('POST', '/orders/$orderId/cancel/'),
      throwsA(
        isA<ApiException>().having((error) => error.statusCode, 'status', 409),
      ),
    );
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
    expect(items.single['status'], 'cancelled');
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

    // Sangria e suprimento nascem PENDENTES, como no servidor: a resposta é
    // o movimento (não a sessão), e é o `status` dele que faz a tela pedir a
    // autorização. Até lá, nada muda no saldo — em nenhum dos dois lados.
    final sangria = await stack.gateway.write(
      'POST',
      '/cash-register/$sessionId/withdrawal/',
      body: {'amount': '50.00', 'reason': 'Sangria do turno'},
    );
    expect(sangria.payload['status'], 'pending');
    expect(sangria.payload['movement_type'], 'withdrawal');
    final suprimento = await stack.gateway.write(
      'POST',
      '/cash-register/$sessionId/supply/',
      body: {'amount': '20.00', 'reason': 'Troco'},
    );
    expect(suprimento.payload['status'], 'pending');
    final antesDeAprovar = await stack.gateway.read('/cash-register/current/');
    expect(ValueFormatters.number(antesDeAprovar['expected_amount']), 150.0);

    // A autorização (senha de ações, conferida sem internet) é o que faz o
    // dinheiro entrar no saldo — aqui e no replay do servidor.
    for (final movimento in [sangria, suprimento]) {
      await stack.gateway.write(
        'POST',
        '/cash-register/$sessionId/approve/',
        body: {
          'movement': movimento.payload['id'],
          'reason': 'ok',
          'cash_password_proof': 'prova',
          'proof_nonce': 'nonce',
        },
      );
    }
    final aprovado = await stack.gateway.read('/cash-register/current/');
    expect(ValueFormatters.number(aprovado['expected_amount']), 120.0);

    final closed = await stack.gateway.write(
      'POST',
      '/cash-register/$sessionId/close/',
      body: {'actual_amount': '120.00'},
    );
    expect(closed.payload['status'], 'closed');
    expect(ValueFormatters.number(closed.payload['difference_amount']), 0);

    // Nenhuma dessas operações se perdeu: todas estão na fila para subir, na
    // ordem — e as aprovações antes do fechamento, que depende delas.
    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(queued.map((entry) => entry.path), [
      '/cash-register/open/',
      '/cash-register/$sessionId/withdrawal/',
      '/cash-register/$sessionId/supply/',
      '/cash-register/$sessionId/approve/',
      '/cash-register/$sessionId/approve/',
      '/cash-register/$sessionId/close/',
    ]);
  });

  test('a gaveta soma em centavos inteiros, sem erro de ponto flutuante', () async {
    // Sete suprimentos de R$ 0,15 são exatamente R$ 1,05. Em `double`, a soma
    // dá 1.0499999999999998 e o fechamento só "batia" por causa de uma
    // tolerância de meio centavo — que também escondia divergência real.
    final opened = await stack.gateway.write(
      'POST',
      '/cash-register/open/',
      body: {'cash_station': 'caixa-1', 'opening_amount': '0.00'},
      context: {
        'cash_station': {'id': 'caixa-1', 'name': 'Caixa 1'},
      },
    );
    final sessionId = '${opened.payload['id']}';
    for (var i = 0; i < 7; i++) {
      final suprimento = await stack.gateway.write(
        'POST',
        '/cash-register/$sessionId/supply/',
        body: {'amount': '0.15', 'reason': 'moedas'},
      );
      await stack.gateway.write(
        'POST',
        '/cash-register/$sessionId/approve/',
        body: {'movement': suprimento.payload['id'], 'reason': 'ok'},
      );
    }
    final atual = await stack.gateway.read('/cash-register/current/');
    expect(atual['expected_amount'], '1.05');

    final closed = await stack.gateway.write(
      'POST',
      '/cash-register/$sessionId/close/',
      body: {'actual_amount': '1.05'},
    );
    expect(closed.payload['status'], 'closed');
    expect(closed.payload['difference_amount'], '0.00');
  });

  test('sangria offline SEM autorização fecha com a diferença à vista', () async {
    // O dinheiro saiu da gaveta mas ninguém autorizou: o saldo esperado não
    // desce, e o fechamento mostra a diferença — a mesma que o servidor vai
    // registrar. Antes o terminal descontava por conta própria e o servidor
    // não; o turno "batia" aqui e chegava lá com uma diferença fantasma.
    final opened = await stack.gateway.write(
      'POST',
      '/cash-register/open/',
      body: {'cash_station': 'caixa-1', 'opening_amount': '100.00'},
      context: {
        'cash_station': {'id': 'caixa-1', 'name': 'Caixa 1'},
      },
    );
    final sessionId = '${opened.payload['id']}';
    await stack.gateway.write(
      'POST',
      '/cash-register/$sessionId/withdrawal/',
      body: {'amount': '30.00', 'reason': 'troco'},
    );
    final closed = await stack.gateway.write(
      'POST',
      '/cash-register/$sessionId/close/',
      body: {'actual_amount': '70.00'},
    );
    expect(closed.payload['status'], 'closed_with_difference');
    expect(ValueFormatters.number(closed.payload['difference_amount']), -30.0);
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

  test(
    'pesagem RELAYADA (sem contexto) resolve o produto pelo cadastro da balança',
    () async {
      // Pela rede local o contexto da janela da balança não viaja: a pesagem
      // de um Caixa Secundário chega ao Principal só com o corpo. Com este
      // terminal sem nuvem, isso estourava `ArgumentError` — 500 no relay,
      // reinsistido a cada cinco minutos até a internet voltar.
      stack.gateway.connectivity = () => false;
      await stack.gateway.repository(EntityCatalog.command).applyRemote({
        'id': 'comanda-9',
        'code': 'CMD-9',
        'number': 9,
        'restaurant': 'rest-1',
      });
      await stack.gateway.repository(EntityCatalog.scale).applyRemote({
        'id': 'balanca-1',
        'name': 'Buffet',
        'restaurant': 'rest-1',
        'product': 'prod-2',
      });

      final result = await stack.gateway.write(
        'POST',
        '/scales/balanca-1/checkout-command/',
        body: {'command_code': 'CMD-9', 'weight_kg': '0.500'},
      );

      final items = (result.payload['items'] as List).cast<Map>();
      expect(items.single['product_name'], 'Buffet por quilo');
      expect(items.single['quantity'], 0.5);
      expect(
        ValueFormatters.number(result.payload['subtotal']),
        closeTo(29.95, 0.001),
      );
    },
  );

  test('balança sem produto por quilo recusa com o motivo, não com 500', () async {
    stack.gateway.connectivity = () => false;
    await stack.gateway.repository(EntityCatalog.scale).applyRemote({
      'id': 'balanca-sem-produto',
      'name': 'Sem produto',
      'restaurant': 'rest-1',
    });

    await expectLater(
      stack.gateway.write(
        'POST',
        '/scales/balanca-sem-produto/checkout-command/',
        body: {'command_code': 'CMD-7', 'weight_kg': '0.400'},
      ),
      throwsA(isA<ApiException>()),
    );
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

  test('consultar, reenviar e cancelar nota não viram documento na fila', () async {
    // As três começam com `/invoices/` e caíam na fila fiscal: cada consulta
    // de autorização criava um DOCUMENTO NOVO, sem pedido (o corpo dessas
    // rotas não tem `order`), que depois tentava emitir sozinho. Consultar a
    // SEFAZ e cancelar uma nota são operações do servidor.
    for (final path in const [
      '/invoices/nota-1/refresh-status/',
      '/invoices/nota-1/resend/',
      '/invoices/nota-1/cancel/',
    ]) {
      expect(
        stack.gateway.handlesWrite('POST', path, const {}),
        isFalse,
        reason: path,
      );
    }
    expect(
      await stack.gateway.fiscalQueue.pendingCount(scope: TestPdvStack.scope),
      0,
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

  group('o pedido nasce com o primeiro item, não antes', () {
    // Entrar numa comanda e escolher a mesa é o operador MONTANDO a venda, não
    // a venda acontecendo. Criar o pedido aí enchia o banco de pedidos vazios
    // — bastava entrar, olhar e sair — e obrigava a inventar um cancelamento
    // para desfazer algo que nunca deveria ter nascido.

    Future<String> abrirComanda({String? mesa}) async {
      await stack.gateway.repository(EntityCatalog.command).applyRemote({
        'id': 'comanda-5',
        'number': 5,
        'restaurant': 'rest-1',
        'status': 'free',
      });
      final opened = await stack.gateway.write(
        'POST',
        '/orders/open-command/',
        body: {'command': 'comanda-5'},
        context: {
          'command': {'id': 'comanda-5', 'number': 5},
          if (mesa != null) 'table': {'id': mesa, 'number': 12},
        },
      );
      return '${opened.payload['id']}';
    }

    test('CASO 1: abrir comanda e sair não deixa nada para o servidor', () async {
      await abrirComanda(mesa: 'mesa-1');

      expect(
        await stack.queue.entries(scope: TestPdvStack.scope),
        isEmpty,
        reason: 'sem item, não há venda — e não há o que sincronizar',
      );
    });

    test('CASO 2: o primeiro item cria o pedido, com mesa e item juntos', () async {
      final orderId = await abrirComanda(mesa: 'mesa-1');

      await stack.gateway.write(
        'POST',
        '/orders/$orderId/items/',
        body: {'product': 'prod-1', 'quantity': 1},
      );

      final queued = await stack.queue.entries(scope: TestPdvStack.scope);
      expect(queued.single.path, '/orders/create-with-item/');
      final body = queued.single.payload!;
      expect(body['order_type'], 'command');
      expect(body['command'], 'comanda-5');
      expect(body['table'], 'mesa-1');
      expect((body['item'] as Map)['product'], 'prod-1');
    });

    test('CASO 3: trocar de mesa antes do item vale a ÚLTIMA escolhida', () async {
      final orderId = await abrirComanda(mesa: 'mesa-1');

      await stack.gateway.write(
        'POST',
        '/commands/comanda-5/link-table/',
        body: {'table_id': 'mesa-9'},
      );
      await stack.gateway.write(
        'POST',
        '/orders/$orderId/items/',
        body: {'product': 'prod-1', 'quantity': 1},
      );

      final criacao = (await stack.queue.entries(scope: TestPdvStack.scope))
          .firstWhere((entry) => entry.path == '/orders/create-with-item/');
      expect(
        criacao.payload!['table'],
        'mesa-9',
        reason: 'a criação levaria a mesa velha ao servidor',
      );
    });

    test('CASO 4: reabrir a tela sem item não gera pedido fantasma', () async {
      final orderId = await abrirComanda(mesa: 'mesa-1');

      // A tela relê o pedido do armazenamento local, como faz ao voltar.
      final relido = await stack.gateway.read('/orders/$orderId/');
      expect(relido['id'], orderId);

      expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
    });

    test(
      'qualquer outra operação faz o rascunho existir antes de si',
      () async {
        // Nem tudo é o primeiro item. Mandar para a cozinha, fechar, receber —
        // qualquer uma dessas precisa de um pedido que o servidor conheça,
        // senão subiria citando um identificador que ninguém pode resolver.
        final orderId = await abrirComanda();

        await stack.gateway.write(
          'POST',
          '/orders/$orderId/send-to-kitchen/',
          body: const {},
        );

        final paths = (await stack.queue.entries(scope: TestPdvStack.scope))
            .map((entry) => entry.path)
            .toList();
        expect(paths.first, '/orders/open-command/');
        expect(paths.last, '/orders/$orderId/send-to-kitchen/');
      },
    );
  });

  group('a comanda volta ao salão sem depender do servidor', () {
    // O caso real: sem rede, a venda foi paga e a comanda continuou ocupada.
    // Quem zera a comanda é `free_command_for_order` no servidor, e ele só
    // roda quando o `pay` chega lá — offline isso é "nunca". O pedido
    // aparecia como pago e a comanda travada, sem receber o próximo cliente e
    // sem nada na tela explicando o motivo.

    Future<String> comandaOcupadaComPedido() async {
      await stack.gateway.repository(EntityCatalog.command).applyRemote({
        'id': 'comanda-9',
        'number': 9,
        'restaurant': 'rest-1',
        'status': 'free',
      });
      final opened = await stack.gateway.write(
        'POST',
        '/orders/open-command/',
        body: {'command': 'comanda-9'},
        context: {
          'command': {'id': 'comanda-9', 'number': 9},
        },
      );
      final orderId = '${opened.payload['id']}';
      await stack.gateway.write(
        'POST',
        '/orders/$orderId/items/',
        body: {'product': 'prod-1', 'quantity': 1},
      );
      // O servidor conhece a comanda como ocupada por esta venda.
      await stack.gateway.repository(EntityCatalog.command).applyRemote({
        'id': 'comanda-9',
        'number': 9,
        'restaurant': 'rest-1',
        'status': 'occupied',
        'current_order_id': orderId,
      }, overwriteLocalChanges: true);
      return orderId;
    }

    Future<Map<String, dynamic>> lerComanda() async =>
        stack.gateway.read('/commands/comanda-9/');

    test('o pagamento total libera a comanda na hora', () async {
      final orderId = await comandaOcupadaComPedido();
      final pedido = await stack.gateway.read('/orders/$orderId/');

      await stack.gateway.write(
        'POST',
        '/orders/$orderId/pay/',
        body: {
          'payment_method': 'metodo-1',
          'amount': '${pedido['total']}',
        },
        context: {
          'payment_method': {'id': 'metodo-1', 'method_type': 'cash'},
        },
      );

      final comanda = await lerComanda();
      expect(comanda['status'], 'free');
      expect(comanda['current_order_id'], isNull);
      expect(comanda['customer_name'], '');
    });

    test('pagamento parcial NÃO libera a comanda', () async {
      final orderId = await comandaOcupadaComPedido();

      await stack.gateway.write(
        'POST',
        '/orders/$orderId/pay/',
        body: {'payment_method': 'metodo-1', 'amount': '1.00'},
        context: {
          'payment_method': {'id': 'metodo-1', 'method_type': 'cash'},
        },
      );

      final comanda = await lerComanda();
      expect(comanda['status'], 'occupied');
      expect(comanda['current_order_id'], isNotNull);
    });

    test(
      'a varredura devolve a comanda que ficou presa numa venda já paga',
      () async {
        // O estado em que as lojas ficaram: comanda ocupada apontando para um
        // pedido que este terminal já considera pago.
        final orderId = await comandaOcupadaComPedido();
        final pedido = await stack.gateway.read('/orders/$orderId/');
        await stack.gateway.orders.applyRemote({
          ...pedido,
          'status': 'paid',
          'payment_status': 'paid',
        }, overwriteLocalChanges: true);

        expect((await lerComanda())['status'], 'occupied');

        final liberadas = await stack.gateway.releaseSettledCommands();

        expect(liberadas, 1);
        final comanda = await lerComanda();
        expect(comanda['status'], 'free');
        expect(comanda['current_order_id'], isNull);
      },
    );

    test('a varredura não mexe em comanda de venda em aberto', () async {
      await comandaOcupadaComPedido();

      expect(await stack.gateway.releaseSettledCommands(), 0);
      expect((await lerComanda())['status'], 'occupied');
    });
  });

  test('sem sessão vinculada o gateway não atende nada', () async {
    stack.gateway.clearSession();

    expect(stack.gateway.handlesRead('/orders/'), isFalse);
    expect(stack.gateway.handlesWrite('POST', '/orders/', const {}), isFalse);
  });

  test('diagnóstico resume fila, fila fiscal e o que existe no banco', () async {
    final aberto = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    // O item é o que faz a venda existir para o servidor — e, portanto, o que
    // aparece na fila.
    await stack.gateway.write(
      'POST',
      '/orders/${aberto.payload['id']}/items/',
      body: {'product': 'prod-1', 'quantity': 1},
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

  // Abrir pela comanda CRIA o pedido. Sem a acao na lista local, `handlesWrite`
  // recusava e a abertura caia na fila legada, que batiza o pedido com a
  // propria chave de idempotencia (`offline-pdv-...`). O pedido passava a
  // existir numa fila e a ser procurado na outra — e o primeiro item lancado
  // estourava "Pedido offline-pdv-... nao existe no armazenamento local".
  test('abrir pedido pela comanda sem rede aceita itens em seguida', () async {
    await stack.gateway.repository(EntityCatalog.command).applyRemote({
      'id': 'comanda-7',
      'restaurant': 'rest-1',
      'number': 7,
      'status': 'free',
    });

    final opened = await stack.gateway.write(
      'POST',
      '/orders/open-command/',
      body: {'command': 'comanda-7'},
      context: {
        'command': {'id': 'comanda-7', 'number': 7},
      },
    );
    final orderId = '${opened.payload['id']}';

    expect(LocalId.isTemporary(orderId), isTrue);
    // O id e do gateway (`offline-<uuid>`), nao a chave da fila legada.
    expect(orderId, isNot(contains('offline-pdv-')));

    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 2},
    );

    final withItem = await stack.gateway.read('/orders/$orderId/');
    expect((withItem['items'] as List), hasLength(1));
    expect(withItem['order_type'], 'command');
  });

  test('pedido com o primeiro item junto tambem nasce local', () async {
    // `/orders/create-with-item/` e o caminho do app do garcom: pedido e
    // primeiro item nascem juntos.
    final created = await stack.gateway.write(
      'POST',
      '/orders/create-with-item/',
      body: {
        'restaurant': 'rest-1',
        'order_type': 'counter',
        'item': {'product': 'prod-1', 'quantity': 1},
      },
    );

    final orderId = '${created.payload['id']}';
    expect(orderId, isNot(contains('offline-pdv-')));
    final stored = await stack.gateway.read('/orders/$orderId/');
    expect((stored['items'] as List), hasLength(1));
  });

}
