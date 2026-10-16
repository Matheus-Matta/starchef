import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/network/api_exception.dart';
import 'package:starchef_pdv_mobile/core/storage/offline_queue_store.dart';
import 'package:starchef_pdv_mobile/core/sync/backend_gateway.dart';
import 'package:starchef_pdv_mobile/core/sync/pending_mutation.dart';
import 'package:starchef_pdv_mobile/features/auth/domain/waiter_session.dart';
import 'package:starchef_pdv_mobile/features/menu/domain/product_options.dart';
import 'package:starchef_pdv_mobile/features/orders/data/order_drafts.dart';
import 'package:starchef_pdv_mobile/features/orders/data/orders_repository.dart';
import 'package:starchef_pdv_mobile/features/orders/presentation/order_detail_presenter.dart';

/// Enviou a rodada, volta para a tela inicial NA HORA: a rodada vai para a
/// fila e sobe em segundo plano — o garçom não fica parado esperando o
/// servidor responder.
class _Gateway extends BackendGateway {
  _Gateway({this.falha = false})
    : super(
        api: ApiClient(baseUrlProvider: () => ''),
        store: OfflineQueueStore(),
      );

  final bool falha;

  final enfileirados = <String>[];
  var foiARede = false;

  @override
  Future<Map<String, dynamic>> mutate({
    required String method,
    required String path,
    required String kind,
    required String summary,
    Map<String, dynamic>? body,
    String? placeholderOrderId,
  }) async {
    foiARede = true;
    return const {};
  }

  @override
  Future<PendingMutation> enqueue({
    required String method,
    required String path,
    required String kind,
    required String summary,
    Map<String, dynamic>? body,
  }) async {
    if (falha) {
      throw const ApiException('Entre novamente para enviar alterações.');
    }
    enfileirados.add(path);
    return PendingMutation(
      operationId: path,
      method: method,
      path: path,
      kind: kind,
      summary: summary,
      createdAt: DateTime(2026),
    );
  }
}

late _Gateway _gateway;

OrderDetailPresenter _presenter({bool falha = false}) => OrderDetailPresenter(
  repository: OrdersRepository(
    api: ApiClient(baseUrlProvider: () => ''),
    gateway: _gateway = _Gateway(falha: falha),
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
  test('rodada vai para a fila em ordem e libera a tela', () async {
    final presenter = _presenter();
    await presenter.addDraft(_coca);

    await presenter.sendToKitchen();

    expect(presenter.roundSent, isTrue);
    expect(presenter.draftItems, isEmpty);
    expect(_gateway.foiARede, isFalse, reason: 'não espera o servidor');
    expect(_gateway.enfileirados, [
      '/orders/o-1/items/',
      '/orders/o-1/send-to-kitchen/',
    ]);
  });

  test('nao conseguiu guardar na fila: fica no pedido com os itens', () async {
    final presenter = _presenter(falha: true);
    await presenter.addDraft(_coca);

    await presenter.sendToKitchen();

    expect(presenter.roundSent, isFalse);
    expect(presenter.draftItems, hasLength(1));
  });
}
