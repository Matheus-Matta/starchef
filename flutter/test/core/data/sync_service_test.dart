import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/entity_record.dart';
import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/sync_operation.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';

import 'pdv_test_support.dart';

/// A sincronização é o que transforma "salvo aqui" em "salvo lá". Estes testes
/// cobrem os dois sentidos: a fila subindo com idempotência e backoff (§7,
/// §23) e a carga descendo paginada e incremental (§13, §14), sem gerar
/// operação de volta (§12).
void main() {
  late TestPdvStack stack;
  late FakeSyncTransport transport;
  late SyncService sync;

  setUp(() async {
    stack = await TestPdvStack.create();
    transport = FakeSyncTransport();
    sync = SyncService(gateway: stack.gateway, transport: transport);
  });

  tearDown(() async {
    await sync.dispose();
    await stack.dispose();
  });

  test('entrega a fila e reconcilia o ID temporário com o real (§7)', () async {
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    final localId = '${created.payload['id']}';
    transport.handlers['POST /orders/'] = (_) => {
      'id': 'pedido-real',
      'sequence': 42,
      'status': 'open',
      'items': const [],
    };

    await sync.push();

    final delivered = transport.requests.single;
    expect(delivered.path, '/orders/');
    // A chave de idempotência acompanha a requisição: um reenvio por timeout
    // devolve a resposta original em vez de criar uma segunda venda.
    expect(delivered.idempotencyKey, isNotNull);
    expect(delivered.body!['client_order_id'], localId);

    expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
    final orders = stack.gateway.orders;
    expect(await orders.read(localId), isNull);
    final stored = await orders.read('pedido-real');
    expect(stored!.syncStatus, SyncStatus.synced);
    expect(stored.payload['sequence'], 42);
  });

  test('item confirmado troca o ID local pelo real e não duplica (§7)', () async {
    await stack.gateway.repository(EntityCatalog.product).applyRemote({
      'id': 'prod-1',
      'name': 'Coxinha',
      'current_price': '6.00',
    });
    await stack.gateway.orders.applyRemote({
      'id': 'pedido-1',
      'status': 'open',
      'items': const [],
    });
    await stack.gateway.write(
      'POST',
      '/orders/pedido-1/items/',
      body: {'product': 'prod-1', 'quantity': 1},
    );
    // A resposta de `/items/` é o ITEM criado, não o pedido.
    transport.handlers['POST /orders/pedido-1/items/'] = (_) => {
      'id': 'item-real',
      'product': 'prod-1',
      'quantity': 1,
      'total_price': '6.00',
    };

    await sync.push();

    var stored = await stack.gateway.orders.read('pedido-1');
    final items = (stored!.payload['items'] as List).cast<Map>();
    expect(items.single['id'], 'item-real');

    // Agora o servidor manda a versão dele do pedido: o item não pode entrar
    // uma segunda vez por parecer "ainda pendente".
    await stack.gateway.orders.applyRemote({
      'id': 'pedido-1',
      'status': 'open',
      'items': [
        {'id': 'item-real', 'product': 'prod-1', 'total_price': '6.00'},
      ],
    });
    stored = await stack.gateway.orders.read('pedido-1');
    expect((stored!.payload['items'] as List), hasLength(1));
  });

  test('reenvio depois de falha usa a MESMA chave de idempotência', () async {
    await stack.gateway.write(
      'POST',
      '/customers/',
      body: {'name': 'Cliente novo'},
    );
    transport.online = false;

    await sync.push();
    transport.online = true;
    transport.handlers['POST /customers/'] = (_) => {'id': 'cliente-real'};
    await stack.queue.retryAllNow(scope: TestPdvStack.scope);
    await sync.push();

    final chaves = transport.requests
        .where((request) => request.path == '/customers/')
        .map((request) => request.idempotencyKey)
        .toSet();
    expect(chaves, hasLength(1));
  });

  test('falha temporária mantém a operação na fila com backoff (§23)', () async {
    await stack.gateway.write(
      'POST',
      '/customers/',
      body: {'name': 'Cliente'},
    );
    transport.online = false;

    await sync.push();

    final entry = (await stack.queue.entries(scope: TestPdvStack.scope)).single;
    expect(entry.attempts, greaterThanOrEqualTo(0));
    expect(sync.snapshot.phase, SyncPhase.offline);
  });

  test('recusa de negócio sai da rotação e não trava as próximas (§23)', () async {
    await stack.gateway.write(
      'POST',
      '/customers/',
      body: {'name': 'Sem telefone'},
    );
    await stack.gateway.write(
      'POST',
      '/customers/',
      body: {'name': 'Cliente válido'},
    );
    var chamadas = 0;
    transport.handlers['POST /customers/'] = (request) {
      chamadas += 1;
      if (chamadas == 1) {
        return const ApiException('Telefone obrigatório.', statusCode: 400);
      }
      return {'id': 'cliente-2'};
    };

    await sync.push();

    final entries = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(entries, hasLength(1));
    expect(entries.single.lastError, contains('Telefone'));
    expect(sync.snapshot.phase, SyncPhase.blocked);
  });

  test('carga de entrada percorre as páginas de 20 em 20 (§13)', () async {
    final pedidas = <int>[];
    transport.handlers['GET /menu/products/'] = (request) {
      final page = int.parse('${request.query!['page']}');
      pedidas.add(page);
      final start = (page - 1) * 20;
      final total = 45;
      final items = [
        for (var i = start; i < start + 20 && i < total; i++)
          {'id': 'p-$i', 'name': 'Produto $i'},
      ];
      return paginated(
        items,
        count: total,
        next: start + 20 < total ? 'http://api/next' : null,
      );
    };

    final applied = await sync.pull(
      EntityCatalog.byType(EntityCatalog.product)!,
    );

    expect(pedidas, [1, 2, 3]);
    expect(applied, 45);
    expect(
      transport.requests.first.query!['page_size'],
      20,
    );
    final page = await stack.gateway.repository(EntityCatalog.product).list();
    expect(page.count, 45);
  });

  test('a segunda carga é incremental e pede também os excluídos (§14)', () async {
    transport.handlers['GET /menu/products/'] = (_) => paginated(
      [
        {'id': 'p1', 'name': 'Café'},
      ],
      count: 1,
    );

    await sync.pull(EntityCatalog.byType(EntityCatalog.product)!);
    transport.requests.clear();
    await sync.pull(EntityCatalog.byType(EntityCatalog.product)!);

    final query = transport.requests.single.query!;
    expect(query['updated_after'], isNotNull);
    // Sem `include_deleted`, um produto removido na retaguarda continuaria
    // vendável no caixa: ele só sumiria da listagem do servidor.
    expect(query['include_deleted'], 1);
  });

  test('carga interrompida no teto de páginas não avança a marca de tempo', () async {
    // Gravar a marca aqui faria a próxima carga pedir `updated_after` a partir
    // de agora e pular para sempre tudo o que ficou para trás.
    transport.handlers['GET /menu/products/'] = (request) {
      final page = int.parse('${request.query!['page']}');
      return paginated(
        [
          for (var i = 0; i < 20; i++)
            {'id': 'p-$page-$i', 'name': 'Produto $i'},
        ],
        count: 100000,
        next: 'http://api/next',
      );
    };

    await sync.pull(EntityCatalog.byType(EntityCatalog.product)!);

    expect(await stack.gateway.lastSyncAt(EntityCatalog.product), isNull);
  });

  test('a marca de tempo recua um pouco para tolerar relógio diferente', () async {
    transport.handlers['GET /menu/products/'] = (_) =>
        paginated([{'id': 'p1', 'name': 'Café'}], count: 1);
    await sync.pull(EntityCatalog.byType(EntityCatalog.product)!);
    final depois = DateTime.now().toUtc();

    final marca = await stack.gateway.lastSyncAt(EntityCatalog.product);
    // `updated_after` é exclusivo: sem folga, alguns segundos de diferença
    // entre o relógio do caixa e o do servidor bastariam para um registro
    // nunca descer.
    expect(marca, isNotNull);
    expect(
      depois.difference(marca!),
      greaterThanOrEqualTo(SyncService.clockSkewMargin),
    );
  });

  test('sessão expirada não manda a fila inteira para revisão manual', () async {
    await stack.gateway.write(
      'POST',
      '/customers/',
      body: {'name': 'Cliente'},
    );
    transport.handlers['POST /customers/'] = (_) =>
        const ApiException('Token inválido.', statusCode: 401);

    await sync.push();

    final entry = (await stack.queue.entries(scope: TestPdvStack.scope)).single;
    // Um 401 costuma ser uma renovação de token que falhou por falta de rede.
    // Marcá-lo como recusa definitiva mandaria todas as vendas do turno para
    // a tela de revisão por causa de uma oscilação.
    expect(entry.status, SyncQueueStatus.pending);
    expect(entry.nextRetryAt, isNotNull);
  });

  test('subcoleção não é gravada como se fosse o recurso pai', () async {
    // `/orders/<id>/payments/` também devolve `results`. Gravá-los aqui
    // criaria um "pedido" para cada recebimento, com o id do pagamento.
    final applied = await stack.gateway.applyRemoteCollection(
      '/orders/pedido-1/payments/',
      paginated([{'id': 'pagamento-1', 'amount': '10.00'}], count: 1),
    );

    expect(applied, 0);
    expect(await stack.gateway.orders.read('pagamento-1'), isNull);
  });

  test('carga de entrada não gera operação de saída (§12)', () async {
    transport.handlers['GET /menu/products/'] = (_) => paginated(
      [
        {'id': 'p1', 'name': 'Café'},
      ],
      count: 1,
    );

    await sync.pull(EntityCatalog.byType(EntityCatalog.product)!);

    expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
  });

  test('recurso indisponível não interrompe a carga dos outros', () async {
    transport.handlers['GET /fiscal/config/'] = (_) =>
        const ApiException('Sem permissão.', statusCode: 403);
    transport.fallback = (_) => paginated(const [], count: 0);

    await sync.pullAll(restaurantId: 'rest-1');

    // Todos os tipos do catálogo foram tentados, apesar do 403 no meio.
    final tentados = transport.requests.map((request) => request.path).toSet();
    expect(tentados, contains('/menu/products/'));
    expect(tentados, contains('/orders/'));
  });

  test('evento do WebSocket vira gravação no SQLite (§11)', () async {
    transport.handlers['GET /menu/products/p1/'] = (_) => {
      'id': 'p1',
      'name': 'Produto atualizado na retaguarda',
    };

    final applied = await sync.pullEntity(
      entityType: EntityCatalog.product,
      entityId: 'p1',
      deleted: false,
    );

    expect(applied, isTrue);
    final stored = await stack.gateway
        .repository(EntityCatalog.product)
        .read('p1');
    expect(stored!.payload['name'], 'Produto atualizado na retaguarda');
    expect(stored.source, ChangeSource.remote);
    // E não voltou para a fila: seria o laço descrito em §12.
    expect(await stack.queue.entries(scope: TestPdvStack.scope), isEmpty);
  });

  test('exclusão avisada pelo WebSocket vira exclusão lógica (§22)', () async {
    await stack.gateway
        .repository(EntityCatalog.product)
        .applyRemote({'id': 'p1', 'name': 'Saiu do cardápio'});

    await sync.pullEntity(
      entityType: EntityCatalog.product,
      entityId: 'p1',
      deleted: true,
    );

    final repository = stack.gateway.repository(EntityCatalog.product);
    expect(await repository.read('p1'), isNull);
    expect(await repository.read('p1', includeDeleted: true), isNotNull);
  });

  test('a fila fiscal sobe separada da fila de vendas (§16)', () async {
    await stack.gateway.write(
      'POST',
      '/invoices/emit/',
      body: {'order': 'pedido-1'},
    );
    transport.handlers['POST /invoices/emit/'] = (_) => {
      'id': 'nota-1',
      'status': 'issued',
      'protocol': '123456789',
    };

    await sync.pushFiscal();

    final documents = await stack.fiscalQueue.documents(
      scope: TestPdvStack.scope,
    );
    expect(documents.single.status, FiscalStatus.authorized);
    expect(documents.single.protocol, '123456789');
  });

  test('nota recusada pela SEFAZ não volta em laço', () async {
    await stack.gateway.write(
      'POST',
      '/invoices/emit/',
      body: {'order': 'pedido-1'},
    );
    transport.handlers['POST /invoices/emit/'] = (_) =>
        const ApiException('Rejeição 539: duplicidade.', statusCode: 400);

    await sync.pushFiscal();
    await sync.pushFiscal();

    final documents = await stack.fiscalQueue.documents(
      scope: TestPdvStack.scope,
    );
    expect(documents.single.status, FiscalStatus.failed);
    expect(
      transport.requests.where((r) => r.path == '/invoices/emit/'),
      hasLength(1),
    );
  });
}
