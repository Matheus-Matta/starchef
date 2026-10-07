import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/network/api_exception.dart';
import 'package:starchef_pdv_mobile/core/storage/offline_queue_store.dart';
import 'package:starchef_pdv_mobile/core/sync/backend_gateway.dart';
import 'package:starchef_pdv_mobile/features/auth/domain/waiter_session.dart';
import 'package:starchef_pdv_mobile/features/menu/domain/product_options.dart';
import 'package:starchef_pdv_mobile/features/orders/data/order_drafts.dart';
import 'package:starchef_pdv_mobile/features/orders/data/orders_repository.dart';
import 'package:starchef_pdv_mobile/features/orders/presentation/order_detail_presenter.dart';

/// Enviou a rodada, volta para a tela inicial: o garçom já vai para a
/// próxima mesa em vez de tocar em "voltar" a cada pedido.
class _Gateway extends BackendGateway {
  _Gateway({this.falha = false})
    : super(
        api: ApiClient(baseUrlProvider: () => ''),
        store: OfflineQueueStore(),
      );

  final bool falha;

  @override
  Future<Map<String, dynamic>> mutate({
    required String method,
    required String path,
    required String kind,
    required String summary,
    Map<String, dynamic>? body,
    String? placeholderOrderId,
  }) async {
    if (falha) {
      throw const ApiException('Produto indisponível', statusCode: 400);
    }
    return {'id': 'o-1', 'items': const [], 'status': 'open'};
  }
}

OrderDetailPresenter _presenter({bool falha = false}) => OrderDetailPresenter(
  repository: OrdersRepository(
    api: ApiClient(baseUrlProvider: () => ''),
    gateway: _Gateway(falha: falha),
    drafts: OrderDrafts(
      testFile: File(
        '${Directory.systemTemp.createTempSync('drafts').path}/d.json',
      ),
    ),
    session: WaiterSession(
      accessToken: 'a',
      refreshToken: 'r',
      user: WaiterUser(
        id: 'u',
        username: 'g',
        name: 'G',
        accountId: 'c',
        restaurantId: 'r',
      ),
    ),
  ),
  subject: OrderSubject.order('o-1'),
  initialOrder: {'id': 'o-1', 'items': const [], 'status': 'open'},
);

const _coca = ProductChoice(productId: 'p1', productName: 'Coca', quantity: 1);

void main() {
  test('rodada enviada: pode voltar ao início', () async {
    final presenter = _presenter();
    await presenter.addDraft(_coca);

    await presenter.sendToKitchen();

    expect(presenter.roundSent, isTrue);
  });

  test('envio recusado: fica no pedido para o garçom resolver', () async {
    final presenter = _presenter(falha: true);
    await presenter.addDraft(_coca);

    await presenter.sendToKitchen();

    expect(presenter.roundSent, isFalse);
  });
}
