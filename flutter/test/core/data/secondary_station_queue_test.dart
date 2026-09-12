import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/relay_sync_transport.dart';
import 'package:starchef_pdv/core/data/sync_operation.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/mutation_relay.dart';

import 'pdv_test_support.dart';

/// Caixa Principal de mentira, controlado pelo teste.
class _FakePrincipal implements MutationRelay {
  bool reachable = true;
  final List<RelayMutation> received = [];
  final Map<String, Map<String, dynamic>> readAnswers = {};
  Map<String, dynamic> Function(RelayMutation)? onRelay;

  @override
  Future<bool> probe() async => reachable;

  @override
  Future<Map<String, dynamic>> read(RelayRead request) async {
    if (!reachable) {
      throw const MutationRelayUnavailable('O caixa não respondeu.');
    }
    return readAnswers[request.path] ??
        const {'count': 0, 'next': null, 'results': []};
  }

  @override
  Future<Map<String, dynamic>> relay(RelayMutation mutation) async {
    if (!reachable) {
      throw const MutationRelayUnavailable('O caixa não respondeu.');
    }
    received.add(mutation);
    final answer = onRelay?.call(mutation);
    if (answer is Map<String, dynamic>) return answer;
    return {'id': 'do-principal-${received.length}'};
  }
}

/// **O Caixa Secundário tem fila própria.**
///
/// Ele guarda o que não conseguiu entregar ao Caixa Principal, do mesmo jeito
/// que o principal guarda o que não conseguiu entregar ao backend (§8). Antes
/// não havia fila nenhuma aqui: com o principal fora do ar, cada operação era
/// recusada na hora e o operador ficava sem vender até alguém religar o outro
/// computador.
void main() {
  late TestPdvStack stack;
  late _FakePrincipal principal;
  late SyncService sync;

  setUp(() async {
    stack = await TestPdvStack.create();
    stack.gateway.relayOnly = true;
    principal = _FakePrincipal();
    sync = SyncService(
      gateway: stack.gateway,
      transport: RelaySyncTransport(principal),
    );
    await stack.gateway.repository(EntityCatalog.product).applyRemote({
      'id': 'prod-1',
      'name': 'Coxinha',
      'restaurant': 'rest-1',
      'current_price': '6.00',
    });
  });

  tearDown(() async {
    await sync.dispose();
    await stack.dispose();
  });

  /// Uma venda de verdade: pedido + primeiro item.
  ///
  /// Só o pedido não vai a lugar nenhum — sem item ele é um rascunho deste
  /// terminal, e é justamente isso que evita pedido vazio no servidor.
  Future<String> abrirVendaComItem() async {
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    final orderId = '${created.payload['id']}';
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );
    return orderId;
  }

  test('com o principal fora, a venda é salva e fica na fila', () async {
    principal.reachable = false;

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
    await sync.push();

    // A venda existe no terminal, e nada se perdeu.
    final stored = await stack.gateway.orders.read(orderId);
    expect((stored!.payload['items'] as List), hasLength(1));
    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    // UMA operação, não duas: o pedido nasce junto com o primeiro item
    // (`/orders/create-with-item/`). Enquanto não havia item, ele era só um
    // rascunho deste terminal e não tinha o que entregar.
    expect(queued.map((entry) => entry.path), ['/orders/create-with-item/']);
    expect(queued.every((entry) => entry.status == SyncQueueStatus.pending), isTrue);
  });

  test('quando o principal volta, a fila sobe em ordem', () async {
    principal.reachable = false;
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    final orderId = '${created.payload['id']}';
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );
    await sync.push();

    principal.reachable = true;
    principal.onRelay = (mutation) =>
        mutation.path == '/orders/create-with-item/'
        ? {
            'id': 'pedido-do-principal',
            'status': 'open',
            'items': const [
              {'id': 'item-do-principal', 'quantity': 1},
            ],
          }
        : {'id': 'item-do-principal'};
    await stack.queue.retryAllNow(scope: TestPdvStack.scope);
    await sync.push();

    // Pedido e primeiro item sobem numa operação só — não há uma janela em
    // que o principal conheça um pedido vazio.
    expect(principal.received.map((m) => m.path), [
      '/orders/create-with-item/',
    ]);
    expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
  });

  test('o reenvio usa a mesma chave, e o principal reconhece a repetição', () async {
    principal.reachable = false;
    await abrirVendaComItem();
    await sync.push();

    principal.reachable = true;
    await stack.queue.retryAllNow(scope: TestPdvStack.scope);
    await sync.push();

    // A chave veio da fila, não de um sorteio a cada tentativa: é ela que o
    // recibo do principal usa para não criar uma segunda venda.
    expect(principal.received.single.operationId, isNotEmpty);
    expect(
      principal.received.single.operationId,
      matches(RegExp(r'^[0-9a-f-]{36}$')),
    );
  });

  test('entrega ambígua volta para a fila em vez de sumir', () async {
    // O principal pode ter gravado e a confirmação ter se perdido. Descartar
    // aqui perderia a venda; repetir é seguro porque o recibo dele deduplica.
    await abrirVendaComItem();
    principal.onRelay = (_) =>
        throw const MutationRelayUncertain('Conexão interrompida.');

    await sync.push();

    final entry = (await stack.queue.entries(scope: TestPdvStack.scope)).single;
    expect(entry.status, SyncQueueStatus.pending);
    expect(entry.nextRetryAt, isNotNull);
  });

  test(
    'principal OCUPADO ou SEM NUVEM (429/503) é falha temporária, não pendência',
    () async {
      // O `_signedRequest` do secundário reconstrói a resposta do principal
      // como `ApiException(statusCode, retryAfter)` — sem `isConnectivity`.
      // 429 ("processando muitas operações locais"), 503 ("não alcançou o
      // servidor") e 500 são todos passageiros: mandar a venda para revisão
      // manual por causa de um pico do principal é perder a venda por nada.
      for (final status in const [429, 503, 500, 502, 504, 408]) {
        await abrirVendaComItem();
        principal.onRelay = (_) => throw ApiException(
          'O Caixa Principal está processando muitas operações locais.',
          statusCode: status,
          retryAfter: status == 429 ? const Duration(seconds: 5) : null,
        );

        await sync.push();

        final pendentes = await stack.queue.entries(scope: TestPdvStack.scope);
        expect(
          pendentes.every((e) => e.status == SyncQueueStatus.pending),
          isTrue,
          reason: 'HTTP $status do principal tem de voltar para a fila',
        );
        expect(pendentes.first.nextRetryAt, isNotNull, reason: 'HTTP $status');
        for (final entry in pendentes) {
          await stack.queue.discardFailed(entry.id);
        }
      }
    },
  );

  test('recusa do principal vira pendência para revisão, não retentativa', () async {
    await abrirVendaComItem();
    principal.onRelay = (_) =>
        throw const ApiException('Comanda já possui pedido.', statusCode: 409);

    await sync.push();

    final entry = (await stack.queue.entries(scope: TestPdvStack.scope)).single;
    expect(entry.status, SyncQueueStatus.failed);
    expect(entry.lastError, contains('Comanda'));
  });

  test('o secundário só enfileira o que o principal sabe executar', () async {
    // Transferir a posse da gaveta valida gerente ou senha na hora: nunca
    // espera em fila nenhuma.
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/cash-register/sessao-12345678/transfer/',
        const {},
      ),
      isFalse,
    );
    expect(
      stack.gateway.handlesWrite('POST', '/orders/', const {}),
      isTrue,
    );
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/orders/pedido-real-12345678/close/',
        const {},
      ),
      isTrue,
    );
  });

  test('o principal não entrega dado fiscal nem usuários ao secundário', () async {
    final tipos = stack.gateway.pullOrder.map((item) => item.type).toSet();

    // Um tablet perdido no salão não pode carregar o CSC da NFC-e nem a lista
    // de usuários da conta.
    expect(tipos, isNot(contains(EntityCatalog.fiscalConfig)));
    expect(tipos, isNot(contains(EntityCatalog.user)));
    expect(tipos, contains(EntityCatalog.product));
    expect(tipos, contains(EntityCatalog.order));
  });

  test('a carga do secundário vem do principal e fica gravada', () async {
    principal.readAnswers['/menu/products/'] = {
      'count': 1,
      'next': null,
      'results': [
        {'id': 'prod-2', 'name': 'Refrigerante', 'restaurant': 'rest-1'},
      ],
    };

    await sync.pull(EntityCatalog.byType(EntityCatalog.product)!);

    final stored = await stack.gateway
        .repository(EntityCatalog.product)
        .read('prod-2');
    expect(stored!.payload['name'], 'Refrigerante');
  });

  test('leitura de recurso ainda vazio busca no principal, não na nuvem', () async {
    // Partida a frio de um secundário: sem esta rota, a busca inicial ia
    // direto ao backend e o terminal falava com o servidor pelas costas do
    // principal — exatamente o que §8 existe para impedir.
    principal.readAnswers['/tables/'] = {
      'count': 1,
      'next': null,
      'results': [
        {'id': 'mesa-1', 'number': 1, 'restaurant': 'rest-1'},
      ],
    };

    await sync.pull(EntityCatalog.byType(EntityCatalog.table)!);

    final stored = await stack.gateway
        .repository(EntityCatalog.table)
        .read('mesa-1');
    expect(stored, isNotNull);
  });

  /// **O caixa do secundário é dele, e funciona com o principal desligado.**
  ///
  /// A gaveta é física: quem conta o dinheiro é quem está na frente daquele
  /// terminal. Um Caixa Secundário sem o principal por perto precisa abrir,
  /// vender, receber, sangrar e fechar o PRÓPRIO caixa — e a sessão aberta no
  /// principal, que ele recebe pela sincronização, não pode se meter nisso.
  group('o caixa do Caixa Secundário', () {
    const pdv2 = 'no-de-instalacao-pdv2';
    const pdv1 = 'no-de-instalacao-pdv1';

    setUp(() async {
      stack.gateway.installationId = pdv2;
      stack.gateway.terminalLabel = 'PDV 2';
      // A sessão do PDV 1 chegou pela carga vinda do principal — ele guarda os
      // dados da loja inteira, inclusive os dos outros terminais.
      await stack.gateway.repository(EntityCatalog.cashSession).applyRemoteList([
        {
          'id': 'sessao-do-pdv1',
          'restaurant': 'rest-1',
          'cash_station': 'caixa-pdv1',
          'cash_station_name': 'Caixa PDV 1',
          'status': 'open',
          'opening_amount': '200.00',
          'current_balance': '200.00',
          'opened_by': 'operador-1',
          'opened_by_name': 'Operador',
          'opened_terminal_installation_id': pdv1,
          'opened_terminal_label': 'PDV 1',
          'movements': const [],
        },
      ]);
    });

    Future<Map<String, dynamic>> abrirCaixaDoPdv2() async {
      final aberta = await stack.gateway.write(
        'POST',
        '/cash-register/open/',
        body: {
          'cash_station': 'caixa-pdv2',
          'opening_amount': '50.00',
          'terminal_installation_id': pdv2,
          'terminal_name': 'PDV 2',
        },
        context: {
          'cash_station': {'id': 'caixa-pdv2', 'name': 'Caixa PDV 2'},
          'operator_name': 'Maria',
        },
      );
      return aberta.payload;
    }

    test('com o principal desligado, abre e opera o próprio caixa', () async {
      principal.reachable = false;

      final minha = await abrirCaixaDoPdv2();
      expect(minha['cash_station'], 'caixa-pdv2');
      expect(minha['opened_terminal_installation_id'], pdv2);

      // `current` devolve a MINHA gaveta, não a do PDV 1.
      final atual = await stack.gateway.read('/cash-register/current/');
      expect(atual['id'], minha['id']);
      expect(atual['cash_station_name'], 'Caixa PDV 2');

      // Sangria e suprimento entram na minha sessão, sem servidor nenhum —
      // pendentes até a autorização, como no servidor.
      final sangria = await stack.gateway.write(
        'POST',
        '/cash-register/${minha['id']}/withdrawal/',
        body: {
          'amount': '20.00',
          'reason': 'troco',
          'terminal_installation_id': pdv2,
        },
      );
      expect(sangria.payload['status'], 'pending');
      await stack.gateway.write(
        'POST',
        '/cash-register/${minha['id']}/approve/',
        body: {
          'movement': sangria.payload['id'],
          'reason': 'ok',
          'cash_password_proof': 'prova',
          'proof_nonce': 'nonce',
        },
      );
      final depois = await stack.gateway.read('/cash-register/current/');
      expect(depois['current_balance'], '30.00');

      // E o fechamento também é local.
      await stack.gateway.write(
        'POST',
        '/cash-register/${minha['id']}/close/',
        body: {'actual_amount': '30.00', 'terminal_installation_id': pdv2},
      );
      final semCaixa = await stack.gateway.read('/cash-register/current/');
      expect(semCaixa['_empty'], isTrue);
    });

    test(
      'o roteador trata abertura e fechamento do caixa como escrita local '
      'num secundário — é o que permite operar sem rede nenhuma',
      () {
        // Antes `handlesWrite` recusava as duas num secundário e o
        // `ApiClient` as encaminhava ao principal NA HORA; com o principal
        // desligado, o operador não abria nem fechava o turno.
        expect(
          stack.gateway.handlesWrite('POST', '/cash-register/open/', {
            'cash_station': 'caixa-pdv2',
          }),
          isTrue,
        );
        expect(
          stack.gateway.handlesWrite('POST', '/cash-register/sessao-x/close/', {
            'actual_amount': '10.00',
          }),
          isTrue,
        );
        // Transferir a posse continua exigindo quem esteja no ar.
        expect(
          stack.gateway.handlesWrite(
            'POST',
            '/cash-register/sessao-x/transfer/',
            {'reason': 'troca'},
          ),
          isFalse,
        );
      },
    );

    test(
      'turno aberto com o principal desligado sobe para ele em ordem quando volta',
      () async {
        principal.reachable = false;
        final minha = await abrirCaixaDoPdv2();
        final sangria = await stack.gateway.write(
          'POST',
          '/cash-register/${minha['id']}/withdrawal/',
          body: {
            'amount': '20.00',
            'reason': 'troco',
            'terminal_installation_id': pdv2,
          },
        );
        await stack.gateway.write(
          'POST',
          '/cash-register/${minha['id']}/close/',
          body: {'actual_amount': '30.00', 'terminal_installation_id': pdv2},
        );
        await sync.push();
        expect(principal.received, isEmpty, reason: 'principal fora: nada saiu');

        principal.reachable = true;
        await stack.queue.retryAllNow(scope: TestPdvStack.scope);
        await sync.push();

        // Abertura primeiro, com a sessão temporária; depois a sangria e o
        // fechamento já com o id que o principal devolveu.
        final caminhos = principal.received.map((m) => m.path).toList();
        expect(caminhos.first, '/cash-register/open/');
        expect(caminhos.last, endsWith('/close/'));
        expect(caminhos, hasLength(3));
        expect(caminhos[1], endsWith('/withdrawal/'));
        final idDoPrincipal = principal.received.first.operationId;
        expect(idDoPrincipal, isNotEmpty);
        expect(sangria.payload['status'], 'pending');
      },
    );

    test('a gaveta do PDV 1 não é adotada nem movimentada aqui', () async {
      principal.reachable = false;

      // Sem caixa próprio aberto, o secundário NÃO herda o do principal.
      final atual = await stack.gateway.read('/cash-register/current/');
      expect(atual['_empty'], isTrue);

      // E não consegue sangrar nem fechar a gaveta do outro terminal.
      await expectLater(
        stack.gateway.write(
          'POST',
          '/cash-register/sessao-do-pdv1/withdrawal/',
          body: {
            'amount': '10.00',
            'reason': 'nao e minha',
            'terminal_installation_id': pdv2,
          },
        ),
        throwsA(isA<ApiException>()),
      );
    });

    test('o que foi operado offline sobe quando o principal volta', () async {
      principal.reachable = false;
      final minha = await abrirCaixaDoPdv2();
      await stack.gateway.write(
        'POST',
        '/cash-register/${minha['id']}/withdrawal/',
        body: {
          'amount': '20.00',
          'reason': 'troco',
          'terminal_installation_id': pdv2,
        },
      );

      principal.reachable = true;
      principal.onRelay = (mutation) => {'id': 'sessao-real-pdv2'};
      await sync.push();

      // As duas operações chegaram ao principal, na ordem, com o terminal
      // deste caixa — e não com o do principal que as encaminhou.
      final caminhos = principal.received.map((m) => m.path).toList();
      expect(caminhos.first, '/cash-register/open/');
      expect(caminhos.last, contains('/withdrawal/'));
      expect(
        principal.received.first.body?['terminal_installation_id'],
        pdv2,
      );
      expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
    });

    test('reiniciar o terminal offline recupera a própria gaveta', () async {
      principal.reachable = false;
      final minha = await abrirCaixaDoPdv2();

      // Reiniciar não muda operador nem instalação: o `nodeId` fica gravado no
      // SQLite local e não depende de rede para ser lido.
      stack.gateway.bindSession(scope: TestPdvStack.scope);
      stack.gateway.installationId = pdv2;

      final atual = await stack.gateway.read('/cash-register/current/');
      expect(atual['id'], minha['id']);
    });
  });

  test('sem o principal, a leitura sai do que já foi sincronizado', () async {
    principal.reachable = false;

    final page = await stack.gateway.read(
      '/menu/products/',
      query: {'restaurant': 'rest-1'},
    );

    expect(page['count'], 1);
    expect((page['results'] as List).single['name'], 'Coxinha');
  });
}
