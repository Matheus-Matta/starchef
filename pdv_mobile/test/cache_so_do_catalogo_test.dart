import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/network/read_cache.dart';
import 'package:starchef_pdv_mobile/core/storage/offline_queue_store.dart';
import 'package:starchef_pdv_mobile/core/sync/backend_gateway.dart';
import 'package:starchef_pdv_mobile/features/auth/domain/waiter_session.dart';
import 'package:starchef_pdv_mobile/features/orders/data/orders_repository.dart';

/// Cardápio e formas de pagamento vêm do cache; pedido, NUNCA.
void main() {
  test('o cardápio é lido uma vez; o pedido toda vez', () async {
    final rotas = <String>[];
    final api = ApiClient(
      baseUrlProvider: () => 'http://loja.local/api/v1',
      httpClient: MockClient((request) async {
        rotas.add(request.url.path);
        return http.Response('{"results": [], "next": null}', 200);
      }),
    );
    final repo = OrdersRepository(
      api: api,
      gateway: BackendGateway(api: api, store: OfflineQueueStore()),
      catalogCache: ReadCache(),
      session: WaiterSession(
        accessToken: 'a',
        refreshToken: 'r',
        user: WaiterUser(
          id: 'u',
          username: 'g',
          name: 'G',
          accountId: 'c',
          restaurantId: 'r1',
        ),
      ),
    );

    await repo.products();
    await repo.products();
    await repo.productCategories();
    await repo.productCategories();
    await repo.paymentMethods();
    await repo.paymentMethods();
    await repo.order('o1');
    await repo.order('o1');

    expect(rotas.where((r) => r.endsWith('/menu/products/')), hasLength(1));
    expect(rotas.where((r) => r.endsWith('/menu/categories/')), hasLength(1));
    expect(rotas.where((r) => r.endsWith('/payments/methods/')), hasLength(1));
    expect(rotas.where((r) => r.endsWith('/orders/o1/')), hasLength(2));
  });
}
