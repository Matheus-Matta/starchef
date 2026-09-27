import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/storage/offline_queue_store.dart';
import 'package:starchef_pdv_mobile/core/sync/backend_gateway.dart';
import 'package:starchef_pdv_mobile/features/auth/domain/waiter_session.dart';
import 'package:starchef_pdv_mobile/features/orders/data/orders_repository.dart';

/// O CÓDIGO PRECISA SUBIR COM O LANÇAMENTO.
///
/// O defeito: num restaurante com `require_operator_code` ligado, abrir pedido
/// e lançar o primeiro item na comanda eram recusados pelo backend — e o app
/// não tinha onde pedir o número. `createOrderWithItem` sequer aceitava o
/// campo, então nenhuma tela poderia tê-lo enviado.
class _GatewayEspiao extends BackendGateway {
  _GatewayEspiao()
    : super(api: ApiClient(baseUrlProvider: () => ''), store: OfflineQueueStore());

  Map<String, dynamic>? corpo;

  @override
  Future<Map<String, dynamic>> mutate({
    required String method,
    required String path,
    required String kind,
    required String summary,
    Map<String, dynamic>? body,
    String? placeholderOrderId,
  }) async {
    corpo = body;
    return {'id': 'o-1'};
  }
}

WaiterSession _sessao({required bool exige}) => WaiterSession(
  accessToken: 'a',
  refreshToken: 'r',
  user: WaiterUser(
    id: 'u-1',
    username: 'garcom',
    name: 'Garçom',
    accountId: 'c-1',
    restaurantId: 'r-1',
    requireOperatorCode: exige,
  ),
);

void main() {
  late _GatewayEspiao gateway;

  OrdersRepository repositorio({bool exige = true}) {
    gateway = _GatewayEspiao();
    return OrdersRepository(
      api: ApiClient(baseUrlProvider: () => ''),
      gateway: gateway,
      session: _sessao(exige: exige),
    );
  }

  test('abrir pedido com o primeiro item leva o código do operador', () async {
    await repositorio().createOrderWithItem(
      orderType: 'counter',
      productId: 'p-1',
      quantity: 1,
      addonIds: const [],
      metafields: const {'operator_code': '4821'},
    );

    // No corpo do PEDIDO, e não só do item: o backend abre a conta com ele e
    // repassa ao primeiro item. Sem isto a abertura inteira era recusada.
    expect(gateway.corpo?['metafields'], {'operator_code': '4821'});
  });

  test('sem código, o campo não vai vazio no corpo', () async {
    // O backend distingue "não informou" de "informou vazio": mandar `{}` num
    // restaurante que exige receberia a recusa sem ninguém ter sido perguntado.
    await repositorio(exige: false).createOrderWithItem(
      orderType: 'counter',
      productId: 'p-1',
      quantity: 1,
      addonIds: const [],
    );

    expect(gateway.corpo?.containsKey('metafields'), isFalse);
  });

  test('anotar na comanda leva o código do operador', () async {
    await repositorio().launchCommandItem(
      commandId: 'cmd-7',
      productId: 'p-1',
      productName: 'Cerveja',
      quantity: 1,
      metafields: const {'operator_code': '4821'},
    );

    expect(gateway.corpo?['metafields'], {'operator_code': '4821'});
  });

  test('a exigência vem da sessão, sem ida à rede', () {
    expect(repositorio().requiresOperatorCode, isTrue);
    expect(repositorio(exige: false).requiresOperatorCode, isFalse);
  });

  test('o guardião é UM por repositório, e atravessa as telas', () {
    // O código é informado no fluxo que abre o atendimento e usado na tela de
    // detalhe. Com um guardião por apresentador, o garçom digitava o código
    // para o primeiro item e era perguntado de novo no segundo.
    final repo = repositorio();
    repo.operatorCodes.guardar('cmd-7', '4821');

    expect(repo.operatorCodes.corpoDe('cmd-7'), {'operator_code': '4821'});
    expect(repo.operatorCodes.corpoDe('cmd-8'), isNull);
  });
}
