import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/local_id.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';

import 'pdv_test_support.dart';

/// O Caixa Principal está NA REDE mas SEM NUVEM — a situação mais comum de
/// queda de internet num restaurante. O secundário entrega a venda a ele, e o
/// principal, offline-first como é, responde com o **id temporário dele**
/// (`offline-...`), porque o servidor ainda não numerou nada.
///
/// Quando a internet volta, o principal troca o temporário pelo definitivo no
/// próprio banco. O secundário, porém, ficou segurando o temporário do
/// principal — e a próxima leitura traz a MESMA venda com o id do servidor.
/// Sem reconciliar, a tela do secundário mostra o pedido duas vezes.
///
/// O protocolo do relay resolve isso com `_client_ids`: o principal anexa aos
/// registros que serve a lista de ids temporários que já promoveu àquele id.
/// Quem tem um deles no banco local troca antes de gravar.
void main() {
  late TestPdvStack stack;
  late FakeSyncTransport transport;
  late SyncService sync;

  setUp(() async {
    stack = await TestPdvStack.create();
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
      {
        'id': 'prod-1',
        'name': 'Pastel',
        'restaurant': 'rest-1',
        'current_price': '7.50',
        'pricing_unit': 'unit',
      },
    ]);
    transport = FakeSyncTransport();
    sync = SyncService(gateway: stack.gateway, transport: transport);
  });

  tearDown(() async {
    await sync.dispose();
    await stack.dispose();
  });

  Future<String> vendaNoSecundario() async {
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

  test(
    'principal sem nuvem responde com id temporário; o definitivo chega depois '
    'e NÃO vira uma segunda venda',
    () async {
      final localId = await vendaNoSecundario();
      expect(LocalId.isTemporary(localId), isTrue);

      // O principal está offline da nuvem: aplica no SQLite dele e responde
      // com o temporário DELE, marcado como enfileirado.
      transport.fallback = (request) => {
        'id': 'offline-principal-1',
        ...?request.body,
        'restaurant': 'rest-1',
        'status': 'open',
        '_local_first': true,
        '_queued_offline': true,
      };
      await sync.push(force: true);

      // O principal sincronizou: o mesmo pedido agora existe como `srv-1`, e
      // ele diz de quais temporários esse id veio.
      await stack.gateway.repository(EntityCatalog.order).applyRemoteList([
        {
          'id': 'srv-1',
          'status': 'open',
          'restaurant': 'rest-1',
          'items': const [],
          'updated_at': DateTime.now().toUtc().toIso8601String(),
          '_client_ids': ['offline-principal-1'],
        },
      ]);

      final page = await stack.gateway.read(
        '/orders/',
        query: {'page': 1, 'page_size': 20, 'restaurant': 'rest-1'},
      );
      final results = (page['results'] as List).cast<Map>();
      expect(
        results,
        hasLength(1),
        reason: 'o pedido temporário e o definitivo são a MESMA venda',
      );
      expect(results.single['id'], 'srv-1');

      // E a tela que ainda segura o id antigo continua encontrando o pedido.
      final promovido = await stack.gateway.read('/orders/$localId/');
      expect(promovido['_empty'], isNot(true));
      expect(promovido['id'], 'srv-1');
    },
  );

  test(
    'registro sem `_client_ids` continua sendo gravado como sempre',
    () async {
      await stack.gateway.repository(EntityCatalog.order).applyRemoteList([
        {
          'id': 'srv-2',
          'status': 'open',
          'restaurant': 'rest-1',
          'items': const [],
        },
      ]);
      final lido = await stack.gateway.read('/orders/srv-2/');
      expect(lido['id'], 'srv-2');
      expect(lido.containsKey('_client_ids'), isFalse);
    },
  );
}
