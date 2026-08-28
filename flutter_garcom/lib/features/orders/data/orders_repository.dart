import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/relay/principal_client.dart';
import '../../../core/relay/relay_gateway.dart';
import '../../../core/relay/relay_signature.dart';
import '../../auth/domain/waiter_session.dart';

/// Pedidos do salão, sempre pela ótica do Caixa Principal.
///
/// **Escrita em pedido já aberto** (item, cancelamento, envio à cozinha,
/// vínculo de mesa): passa pelo [gateway] — se o caixa estiver inalcançável,
/// fica salva no aparelho e é reenviada sozinha quando a conexão voltar (ver
/// [RelayGateway]).
///
/// **Abrir um pedido novo** (comanda, balcão, delivery, retirada): vai direto
/// pelo [principalClient], sem fila. Não dá para enfileirar com segurança:
/// sem o caixa responder não existe id de pedido nenhum para anexar os itens
/// que o garçom for lançando em seguida — a falha aparece na hora, com a
/// mensagem de conexão.
///
/// **Leitura**: tenta o principal primeiro (é a mesma verdade que o caixa
/// enxerga, e funciona com a internet da loja caída) e cai para o backend
/// quando o principal não responde.
class OrdersRepository {
  OrdersRepository({
    required this.api,
    required this.principalClient,
    required this.gateway,
    required this.session,
    required this.principal,
  });

  final ApiClient api;
  final PrincipalClient principalClient;
  final RelayGateway gateway;
  final WaiterSession session;

  /// Pareamento do aparelho — do dispositivo, não do garçom (ver
  /// `SessionStorage`).
  final PrincipalConfig principal;

  /// Página pequena de propósito: o aparelho é um celular no meio do salão,
  /// muitas vezes no limite do Wi-Fi. Mais páginas curtas respondem melhor do
  /// que uma longa que trava a tela.
  static const _pageSize = 30;

  /// Pedidos em aberto do restaurante do garçom.
  Future<List<Map<String, dynamic>>> openOrders() async {
    final page = await _read(
      '/orders/',
      query: {
        'status': 'open',
        'restaurant': session.user.restaurantId,
        'ordering': '-opened_at',
        'page_size': 50,
      },
    );
    return _rows(page);
  }

  Future<Map<String, dynamic>> order(String id) => _read('/orders/$id/');

  /// Mesas do restaurante, para vincular a uma comanda.
  Future<List<Map<String, dynamic>>> tables() async {
    final page = await _read(
      '/tables/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'page_size': 100,
        'ordering': 'number',
      },
    );
    return _rows(page);
  }

  /// Comandas do restaurante — a porta de entrada do pedido de salão.
  Future<ResourcePage> commands({int page = 1, String search = ''}) async {
    final response = await _read(
      '/commands/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'ordering': 'number',
        'page': page,
        'page_size': _pageSize,
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    return ResourcePage.from(response);
  }

  /// Catálogo vendável, uma página por vez.
  ///
  /// Baixar tudo de uma vez travava a abertura da busca em cardápios grandes e
  /// gastava a franquia de dados do aparelho do garçom à toa: ele digita o
  /// nome e escolhe entre os primeiros resultados.
  Future<ResourcePage> products({int page = 1, String search = ''}) async {
    final response = await _read(
      '/menu/products/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'ordering': 'name',
        'page': page,
        'page_size': _pageSize,
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    return ResourcePage.from(response);
  }

  /// Abre (ou retoma) o pedido de uma comanda. Entra na fila offline (ver
  /// [_mutateCreate]) se o caixa estiver fora do ar.
  ///
  /// O backend devolve 201 para comanda livre e 200 quando já havia pedido
  /// aberto — nos dois casos vem o pedido, que é o que o app precisa.
  Future<Map<String, dynamic>> openCommandOrder(String commandId) =>
      _mutateCreate(
        path: '/orders/open-command/',
        summary: 'Abrir comanda',
        body: {'command': commandId},
        optimisticFields: {'order_type': 'command', 'command': commandId},
      );

  /// Pedido sem comanda: balcão, delivery ou retirada. Entra na fila offline
  /// (ver [_mutateCreate]) se o caixa estiver fora do ar.
  ///
  /// `table` não é aceito como tipo: pedido de salão nasce em comanda e a mesa
  /// entra depois como vínculo (ver [linkTable]).
  Future<Map<String, dynamic>> createOrder(String orderType) => _mutateCreate(
    path: '/orders/',
    summary: 'Novo pedido',
    body: {'order_type': orderType},
    optimisticFields: {'order_type': orderType},
  );

  /// Materializa um rascunho somente junto com o primeiro item confirmado.
  /// Entra na fila offline (ver [_mutateCreate]) se o caixa estiver fora do
  /// ar.
  Future<Map<String, dynamic>> createOrderWithItem({
    required String orderType,
    required String productId,
    required int quantity,
    required List<String> addonIds,
    String? variationId,
    String customerNote = '',
    String? commandId,
    String? tableId,
  }) {
    final item = {
      'product': productId,
      'quantity': quantity,
      'variations': variationId == null ? const [] : [variationId],
      'addons': addonIds,
      'customer_note': customerNote,
    };
    return _mutateCreate(
      path: '/orders/create-with-item/',
      summary: 'Novo pedido',
      body: {
        'order_type': orderType,
        ...commandId == null ? const {} : {'command': commandId},
        ...tableId == null ? const {} : {'table': tableId},
        'item': item,
      },
      optimisticFields: {
        'order_type': orderType,
        'command': ?commandId,
        'table': ?tableId,
        'items': [
          {...item, 'status': 'pending'},
        ],
      },
    );
  }

  /// Cria um pedido novo passando pelo [gateway]: com o caixa fora do ar, a
  /// criação fica salva no aparelho (mesmo mecanismo de [_mutate]) e esta
  /// função devolve um pedido "otimista" na hora — com um id local
  /// (`offline-...`) — em vez de lançar erro, para o garçom continuar
  /// trabalhando nele sem esperar a rede voltar. `RelayGateway` troca o id
  /// local pelo real sozinho assim que a criação sincronizar.
  Future<Map<String, dynamic>> _mutateCreate({
    required String path,
    required String summary,
    required Map<String, dynamic> body,
    required Map<String, dynamic> optimisticFields,
  }) async {
    final placeholderId = 'offline-${RelaySignature.randomId()}';
    try {
      return await gateway.mutate(
        method: 'POST',
        path: path,
        kind: 'create_order',
        summary: summary,
        body: body,
        placeholderOrderId: placeholderId,
      );
    } on MutationQueued {
      return {
        'id': placeholderId,
        '_offline_pending': true,
        'status': 'open',
        'payment_status': 'pending',
        'items': const [],
        ...optimisticFields,
      };
    }
  }

  /// Vincula a comanda a uma mesa (onde o cliente sentou). Entra na fila se o
  /// caixa estiver fora do ar.
  Future<Map<String, dynamic>> linkTable({
    required String commandId,
    required String tableId,
    required String tableLabel,
  }) => _mutate(
    method: 'POST',
    path: '/commands/$commandId/link-table/',
    kind: 'link_table',
    summary: 'Vincular à mesa $tableLabel',
    body: {'table_id': tableId},
  );

  Future<Map<String, dynamic>> unlinkTable({required String commandId}) =>
      _mutate(
        method: 'POST',
        path: '/commands/$commandId/unlink-table/',
        kind: 'unlink_table',
        summary: 'Desvincular comanda da mesa',
      );

  /// Entra na fila se o caixa estiver fora do ar.
  Future<Map<String, dynamic>> addItem({
    required String orderId,
    required String productId,
    required String productName,
    required int quantity,
    String customerNote = '',
    List<String> addonIds = const [],
    String? variationId,
  }) => _mutate(
    method: 'POST',
    path: '/orders/$orderId/items/',
    kind: 'add_item',
    summary: '${quantity}x $productName',
    body: {
      'product': productId,
      'quantity': quantity,
      'variations': variationId == null ? const [] : [variationId],
      'addons': addonIds,
      'customer_note': customerNote,
    },
  );

  /// Entra na fila se o caixa estiver fora do ar.
  Future<Map<String, dynamic>> voidItem({
    required String orderId,
    required String itemId,
    required String itemLabel,
    required String reason,
  }) => _mutate(
    method: 'DELETE',
    path: '/orders/$orderId/items/$itemId/void/',
    kind: 'void_item',
    summary: 'Cancelar $itemLabel',
    body: {'reason': reason},
  );

  /// Manda para a cozinha — é aqui que o principal imprime. Entra na fila se
  /// o caixa estiver fora do ar: a impressão acontece assim que ele voltar.
  Future<Map<String, dynamic>> sendToKitchen(String orderId) => _mutate(
    method: 'POST',
    path: '/orders/$orderId/send-to-kitchen/',
    kind: 'send_to_kitchen',
    summary: 'Enviar pedido para a cozinha',
  );

  /// Passa pelo [gateway]: sem conexão, fica salvo e reenvia sozinho (ver
  /// [RelayGateway]).
  Future<Map<String, dynamic>> _mutate({
    required String method,
    required String path,
    required String kind,
    required String summary,
    Map<String, dynamic>? body,
  }) => gateway.mutate(
    method: method,
    path: path,
    kind: kind,
    summary: summary,
    body: body,
  );

  Future<Map<String, dynamic>> _read(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    try {
      return await principalClient.read(
        principal,
        session.identity,
        path: path,
        query: query,
      );
    } on PrincipalUnavailable {
      return api.get(path, query: query, accessToken: session.accessToken);
    } on ApiException catch (error) {
      // Um erro vindo do backend através do principal já é a resposta final —
      // repetir pela nuvem só daria o mesmo erro mais devagar.
      if (error.statusCode != null) rethrow;
      return api.get(path, query: query, accessToken: session.accessToken);
    }
  }

  static List<Map<String, dynamic>> _rows(Map<String, dynamic> page) {
    final results = page['results'] ?? page['data'];
    if (results is List) {
      return results
          .whereType<Map>()
          .map(Map<String, dynamic>.from)
          .toList(growable: false);
    }
    return const [];
  }
}

/// Uma página da API (DRF): as linhas e se ainda há mais para buscar.
class ResourcePage {
  const ResourcePage({required this.rows, required this.hasMore});

  final List<Map<String, dynamic>> rows;
  final bool hasMore;

  static ResourcePage from(Map<String, dynamic> payload) {
    final results = payload['results'];
    return ResourcePage(
      rows: results is List
          ? results.whereType<Map>().map(Map<String, dynamic>.from).toList()
          : const [],
      // `next` nulo é o fim da lista — é o próprio DRF dizendo, sem o app ter
      // de adivinhar por contagem.
      hasMore: payload['next'] != null,
    );
  }
}
