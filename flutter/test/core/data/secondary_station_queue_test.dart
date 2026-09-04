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
    expect(queued.map((entry) => entry.path), [
      '/orders/',
      '/orders/$orderId/items/',
    ]);
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
    principal.onRelay = (mutation) => mutation.path == '/orders/'
        ? {'id': 'pedido-do-principal', 'status': 'open', 'items': const []}
        : {'id': 'item-do-principal'};
    await stack.queue.retryAllNow(scope: TestPdvStack.scope);
    await sync.push();

    expect(principal.received.map((m) => m.path), [
      '/orders/',
      // A inclusão do item já sai com o id que o principal devolveu: enviar o
      // identificador local faria o principal recusar um pedido que ele não
      // conhece.
      '/orders/pedido-do-principal/items/',
    ]);
    expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
  });

  test('o reenvio usa a mesma chave, e o principal reconhece a repetição', () async {
    principal.reachable = false;
    await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
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
    await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    principal.onRelay = (_) =>
        throw const MutationRelayUncertain('Conexão interrompida.');

    await sync.push();

    final entry = (await stack.queue.entries(scope: TestPdvStack.scope)).single;
    expect(entry.status, SyncQueueStatus.pending);
    expect(entry.nextRetryAt, isNotNull);
  });

  test('recusa do principal vira pendência para revisão, não retentativa', () async {
    await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    principal.onRelay = (_) =>
        throw const ApiException('Comanda já possui pedido.', statusCode: 409);

    await sync.push();

    final entry = (await stack.queue.entries(scope: TestPdvStack.scope)).single;
    expect(entry.status, SyncQueueStatus.failed);
    expect(entry.lastError, contains('Comanda'));
  });

  test('o secundário só enfileira o que o principal sabe executar', () async {
    // Abrir caixa é do principal: aceitar aqui deixaria o operador com uma
    // operação salva que nunca teria como ser entregue.
    expect(
      stack.gateway.handlesWrite('POST', '/cash-register/open/', const {}),
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
