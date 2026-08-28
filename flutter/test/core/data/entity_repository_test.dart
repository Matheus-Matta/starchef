import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/entity_record.dart';
import 'package:starchef_pdv/core/data/sync_operation.dart';

import 'pdv_test_support.dart';

/// O repositório é a única porta para o banco (§27). Estes testes cobrem o que
/// a arquitetura offline exige dele: gravar entidade e operação de fila na
/// mesma transação (§5), paginar localmente (§13), versionar (§21), excluir
/// logicamente (§22) e não deixar uma alteração remota atropelar o que o
/// operador acabou de lançar (§12).
void main() {
  late TestPdvStack stack;

  setUp(() async => stack = await TestPdvStack.create());
  tearDown(() async => stack.dispose());

  test(
    'gravação local cria a entidade e a operação de fila na mesma transação',
    () async {
      final products = stack.gateway.repository(EntityCatalog.product);

      final write = await products.saveLocal(
        {'id': 'produto-1', 'name': 'Coxinha', 'restaurant': 'rest-1'},
        operation: SyncOperation.create,
        method: 'POST',
        path: '/menu/products/',
      );

      final stored = await products.read('produto-1');
      expect(stored, isNotNull);
      expect(stored!.payload['name'], 'Coxinha');
      expect(stored.syncStatus, SyncStatus.pending);
      expect(stored.source, ChangeSource.local);

      final queued = await stack.queue.entries(scope: TestPdvStack.scope);
      expect(queued, hasLength(1));
      expect(queued.single.operationId, write.operationId);
      expect(queued.single.path, '/menu/products/');
      expect(queued.single.entityId, 'produto-1');
    },
  );

  test('paginação local devolve páginas de 20 e não repete a última', () async {
    final products = stack.gateway.repository(EntityCatalog.product);
    await products.applyRemoteList([
      for (var i = 0; i < 45; i++)
        {'id': 'p-${i.toString().padLeft(3, '0')}', 'name': 'Item $i'},
    ]);

    final first = await products.list(query: {'page': 1, 'page_size': 20});
    final third = await products.list(query: {'page': 3, 'page_size': 20});
    final beyond = await products.list(query: {'page': 4, 'page_size': 20});

    expect(first.count, 45);
    expect(first.results, hasLength(20));
    expect(first.hasNext, isTrue);
    expect(third.results, hasLength(5));
    // Uma página além do fim é uma página vazia — nunca a anterior de novo.
    expect(beyond.results, isEmpty);
    expect(beyond.hasNext, isFalse);
  });

  test('filtra pelas colunas indexadas e pelos campos livres do payload', () async {
    final products = stack.gateway.repository(EntityCatalog.product);
    await products.applyRemoteList([
      {'id': 'p1', 'name': 'Suco', 'restaurant': 'rest-1', 'is_active': true},
      {'id': 'p2', 'name': 'Bolo', 'restaurant': 'rest-2', 'is_active': true},
      {
        'id': 'p3',
        'name': 'Pastel',
        'restaurant': 'rest-1',
        'is_active': true,
        'category': 'cat-9',
      },
    ]);

    final byRestaurant = await products.list(query: {'restaurant': 'rest-1'});
    final byCategory = await products.list(query: {'category': 'cat-9'});
    final bySearch = await products.list(query: {'search': 'bol'});

    // Cardápio sai em ordem alfabética, como a API devolve: Pastel, Suco.
    expect(byRestaurant.results.map((item) => item['id']), ['p3', 'p1']);
    expect(byCategory.results.single['id'], 'p3');
    expect(bySearch.results.single['id'], 'p2');
  });

  test('um filtro por campo inexistente não esconde o registro', () async {
    // O backend ignora parâmetros que não conhece; divergir disso deixaria a
    // tela vazia sem nenhuma explicação.
    final tables = stack.gateway.repository(EntityCatalog.table);
    await tables.applyRemoteList([
      {'id': 't1', 'name': 'Mesa 1', 'restaurant': 'rest-1'},
    ]);

    final page = await tables.list(query: {'campo_inventado': 'x'});

    expect(page.results, hasLength(1));
  });

  test('versão sobe a cada gravação local e guarda a versão do servidor', () async {
    final customers = stack.gateway.repository(EntityCatalog.customer);
    await customers.saveLocal(
      {'id': 'c1', 'name': 'Ana'},
      operation: SyncOperation.create,
      method: 'POST',
      path: '/customers/',
    );
    await customers.saveLocal(
      {'id': 'c1', 'name': 'Ana Maria'},
      operation: SyncOperation.update,
      method: 'PATCH',
      path: '/customers/c1/',
    );

    final stored = await customers.read('c1');
    expect(stored!.version, 2);
    expect(stored.serverVersion, isNull);

    // Só a última entrega zera a pendência: enquanto restar operação na fila
    // para esta entidade, ela continua pendente — senão uma leitura vinda do
    // servidor apagaria o que ainda não subiu.
    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    await customers.markSynced(
      'c1',
      ignoreQueuedOperationId: queued.first.operationId,
    );
    expect((await customers.read('c1'))!.syncStatus, SyncStatus.pending);

    await stack.queue.markSynced(queued.first.id);
    await customers.markSynced('c1', serverPayload: {
      'id': 'c1',
      'name': 'Ana Maria',
      'updated_at': '2026-08-28T10:00:00Z',
    }, ignoreQueuedOperationId: queued.last.operationId);
    final synced = await customers.read('c1');
    expect(synced!.syncStatus, SyncStatus.synced);
    expect(synced.serverVersion, '2026-08-28T10:00:00Z');
  });

  test('alteração remota não atropela o que ainda não subiu (§12)', () async {
    final customers = stack.gateway.repository(EntityCatalog.customer);
    await customers.saveLocal(
      {'id': 'c1', 'name': 'Nome digitado no caixa'},
      operation: SyncOperation.update,
      method: 'PATCH',
      path: '/customers/c1/',
    );

    final applied = await customers.applyRemote({
      'id': 'c1',
      'name': 'Nome antigo do servidor',
    });

    expect(applied, isNull);
    final stored = await customers.read('c1');
    expect(stored!.payload['name'], 'Nome digitado no caixa');
  });

  test('aplicar do servidor não gera operação de saída (§12)', () async {
    final products = stack.gateway.repository(EntityCatalog.product);

    await products.applyRemote({'id': 'p1', 'name': 'Do servidor'});

    final queued = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(queued, isEmpty);
    final stored = await products.read('p1');
    expect(stored!.source, ChangeSource.remote);
    expect(stored.syncStatus, SyncStatus.synced);
  });

  test('pedido do servidor e criado offline dividem a mesma ordenação', () async {
    // A chave de ordenação já misturou duas escalas: `sequence` numérico para
    // o que veio do servidor e data ISO para o que nasceu offline. Como a
    // comparação é textual, TODOS os pedidos do servidor caíam depois de
    // todos os locais, e a lista deixava de ser "mais recente primeiro".
    final orders = stack.gateway.orders;
    await orders.applyRemote({
      'id': 'do-servidor-antigo',
      'sequence': 41,
      'created_at': '2026-08-28T09:00:00Z',
      'items': const [],
    });
    await orders.applyRemote({
      'id': 'do-servidor-novo',
      'sequence': 42,
      'created_at': '2026-08-28T11:00:00Z',
      'items': const [],
    });
    await orders.saveLocal(
      {
        'id': 'offline-agora',
        'sequence': 'LOCAL-ABC',
        'created_at': '2026-08-28T10:00:00Z',
        'items': const [],
      },
      operation: SyncOperation.create,
      method: 'POST',
      path: '/orders/',
    );

    final page = await orders.list();

    expect(page.results.map((item) => item['id']), [
      'do-servidor-novo',
      'offline-agora',
      'do-servidor-antigo',
    ]);
  });

  test('registro ilegível é pulado sem derrubar a listagem', () async {
    final products = stack.gateway.repository(EntityCatalog.product);
    await products.applyRemoteList([
      {'id': 'p1', 'name': 'Bom'},
      {'id': 'p2', 'name': 'Corrompido'},
    ]);
    // Simula o que acontece quando a chave do cofre muda entre reinstalações
    // no Linux: o payload existe, mas não pode ser interpretado.
    await stack.database.execute(
      "UPDATE entities SET payload = 'enc:v1:AAA:BBB:CCC' "
      'WHERE entity_id = ?',
      ['p2'],
    );

    final page = await products.list();

    expect(page.results.map((item) => item['id']), ['p1']);
  });

  test('evento fora de ordem não desfaz uma atualização já recebida', () async {
    // WebSocket e sincronização periódica correm juntos: a mesma entidade
    // chega duas vezes e a segunda pode ser a mais antiga.
    final products = stack.gateway.repository(EntityCatalog.product);
    await products.applyRemote({
      'id': 'p1',
      'name': 'Preço novo',
      'updated_at': '2026-08-28T12:00:00Z',
    });

    final atrasado = await products.applyRemote({
      'id': 'p1',
      'name': 'Preço antigo',
      'updated_at': '2026-08-28T11:00:00Z',
    });

    expect(atrasado, isNull);
    expect((await products.read('p1'))!.payload['name'], 'Preço novo');
  });

  test('exclusão é lógica e some das listagens (§22)', () async {
    final products = stack.gateway.repository(EntityCatalog.product);
    await products.applyRemote({'id': 'p1', 'name': 'Sai do cardápio'});

    await products.markRemoteDeleted('p1');

    expect((await products.list()).results, isEmpty);
    expect(await products.read('p1'), isNull);
    // O registro continua no banco: é o que permite avisar o servidor depois.
    expect(await products.read('p1', includeDeleted: true), isNotNull);
  });

  test('metadados de transporte não são persistidos no registro', () async {
    final products = stack.gateway.repository(EntityCatalog.product);

    final write = await products.saveLocal(
      {'id': 'p1', 'name': 'Café', '_offline_pending': true, '_local': true},
      operation: SyncOperation.create,
      method: 'POST',
      path: '/menu/products/',
    );
    await products.markSynced('p1', ignoreQueuedOperationId: write.operationId);

    final stored = await products.read('p1');
    // `_offline_pending` volta a aparecer apenas enquanto o registro estiver
    // pendente; gravado no payload, ele ficaria colado para sempre.
    expect(stored!.payload.containsKey('_offline_pending'), isFalse);
    expect(stored.toApiJson().containsKey('_offline_pending'), isFalse);
  });

  test('troca o ID temporário pelo definitivo e registra o mapeamento', () async {
    final customers = stack.gateway.repository(EntityCatalog.customer);
    await customers.saveLocal(
      {'id': 'offline-abc', 'name': 'Cliente novo'},
      operation: SyncOperation.create,
      method: 'POST',
      path: '/customers/',
    );

    await customers.replaceId('offline-abc', 'c-real');

    expect(await customers.read('offline-abc'), isNull);
    final stored = await customers.read('c-real');
    expect(stored!.payload['name'], 'Cliente novo');
    final mappings = await stack.queue.resolvedIds(scope: TestPdvStack.scope);
    expect(mappings['offline-abc'], 'c-real');
  });
}
