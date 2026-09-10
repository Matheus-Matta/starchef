import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/sync_operation.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';

import 'pdv_test_support.dart';

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

  Future<void> enqueue(String entityId, String path) => stack.queue.enqueue(
    scope: TestPdvStack.scope,
    entityType: EntityCatalog.order,
    entityId: entityId,
    operation: SyncOperation.update,
    method: 'POST',
    path: path,
  );

  test('descartar uma recusa remove finalizações derivadas', () async {
    await enqueue('pedido-1', '/orders/pedido-1/close/');
    await enqueue('pedido-1', '/orders/pedido-1/pay/');
    await enqueue('pedido-2', '/orders/pedido-2/close/');
    final close = await stack.queue.claimNext(scope: TestPdvStack.scope);
    await stack.queue.markFailed(close!.id, error: 'Total divergente.');

    expect(await stack.queue.discardFailed(close.id), isTrue);

    final remaining = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(remaining, hasLength(1));
    expect(remaining.single.entityId, 'pedido-2');
  });

  test('NFC-e espera todas as mutações do pedido serem confirmadas', () async {
    await enqueue('pedido-1', '/orders/pedido-1/pay/');
    await stack.gateway.write(
      'POST',
      '/invoices/emit/',
      body: {'order': 'pedido-1'},
    );
    transport.handlers['POST /invoices/emit/'] = (_) => {
      'id': 'nota-1',
      'fiscal_state': 'authorized',
    };

    await sync.pushFiscal(orderId: 'pedido-1');
    expect(transport.requests, isEmpty);

    final payment = await stack.queue.claimNext(scope: TestPdvStack.scope);
    await stack.queue.markSynced(payment!.id);
    await sync.pushFiscal(orderId: 'pedido-1');
    expect(transport.requests.single.path, '/invoices/emit/');
  });

  test('promoção do pedido também atualiza a fila fiscal', () async {
    await stack.gateway.write(
      'POST',
      '/invoices/emit/',
      body: {'order': 'offline-pedido'},
    );

    await stack.queue.registerResolvedId(
      scope: TestPdvStack.scope,
      localId: 'offline-pedido',
      remoteId: 'pedido-real',
    );

    final document = (await stack.fiscalQueue.documents(
      scope: TestPdvStack.scope,
    )).single;
    expect(document.orderId, 'pedido-real');
    expect(document.payload['order'], 'pedido-real');
  });

  test('pagamento local preserva o subtipo usado pela NFC-e', () async {
    await stack.gateway.orders.applyRemote({
      'id': 'pedido-1',
      'status': 'awaiting_payment',
      'payment_status': 'pending',
      'total': '10.00',
      'items': const [],
      'payments': const [],
    });

    await stack.gateway.write(
      'POST',
      '/orders/pedido-1/pay/',
      body: {
        'payment_method': 'cartao-1',
        'amount': '10.00',
        'metadata': {'card_subtype': 'credit'},
      },
      context: {
        'payment_method': {
          'id': 'cartao-1',
          'name': 'Cartão',
          'method_type': 'card',
        },
      },
    );

    final stored = await stack.gateway.orders.read('pedido-1');
    final payment = (stored!.payload['offline_payments'] as List).single as Map;
    expect(payment['card_subtype'], 'credit');

    await stack.gateway.orders.removeRejectedPayments('pedido-1', {
      '${payment['id']}',
    });
    final recovered = await stack.gateway.orders.read('pedido-1');
    expect(recovered!.payload['offline_payments'], isEmpty);
    expect(recovered.payload['payment_status'], 'pending');
    expect(recovered.payload['status'], 'open');
  });
}
