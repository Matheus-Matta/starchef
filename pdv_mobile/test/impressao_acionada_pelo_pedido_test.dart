import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/storage/offline_queue_store.dart';
import 'package:starchef_pdv_mobile/core/sync/backend_gateway.dart';
import 'package:starchef_pdv_mobile/features/auth/domain/waiter_session.dart';
import 'package:starchef_pdv_mobile/features/orders/data/orders_repository.dart';

void main() {
  test('envio e cancelamento acordam a impressao imediatamente', () async {
    var atualizacoes = 0;
    final repository = OrdersRepository(
      api: ApiClient(baseUrlProvider: () => ''),
      gateway: _GatewayEspiao(),
      session: _sessao(),
      onPrintJobsCreated: () => atualizacoes++,
    );

    await repository.sendToKitchen('pedido-1');
    await repository.voidItem(
      orderId: 'pedido-1',
      itemId: 'item-1',
      itemLabel: 'X-Burger',
      reason: 'Cliente desistiu',
    );
    await repository.sendCommandToKitchen('comanda-1');
    await repository.voidCommandItem(
      commandId: 'comanda-1',
      itemId: 'item-2',
      itemLabel: 'Suco',
      reason: 'Cliente desistiu',
    );

    expect(atualizacoes, 4);
  });
}

class _GatewayEspiao extends BackendGateway {
  _GatewayEspiao()
    : super(
        api: ApiClient(baseUrlProvider: () => ''),
        store: OfflineQueueStore(),
      );

  @override
  Future<Map<String, dynamic>> mutate({
    required String method,
    required String path,
    required String kind,
    required String summary,
    Map<String, dynamic>? body,
    String? placeholderOrderId,
  }) async => <String, dynamic>{};
}

WaiterSession _sessao() => const WaiterSession(
  accessToken: 'a',
  refreshToken: 'r',
  user: WaiterUser(
    id: 'u-1',
    username: 'garcom',
    name: 'Garcom',
    accountId: 'c-1',
    restaurantId: 'r-1',
  ),
);
