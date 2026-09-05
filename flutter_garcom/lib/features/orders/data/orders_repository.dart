import 'dart:async';

import '../../../core/network/api_exception.dart';
import '../../../core/network/resource_page.dart';
import '../../../core/relay/principal_client.dart';
import '../../../core/relay/relay_gateway.dart';
import '../../../core/relay/relay_signature.dart';
import '../../../core/storage/principal_cache.dart';
import '../../auth/domain/waiter_session.dart';
import 'order_drafts.dart';

/// Reexportado para quem consome o repositório não precisar saber que a
/// página paginada é um tipo do núcleo — a lista de escolha (`PaginatedPicker`)
/// fala o mesmo tipo, e é o que evita converter registro em classe no meio do
/// caminho.
export '../../../core/network/resource_page.dart';

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
/// **Leitura**: SEMPRE pelo principal, nunca pela API externa (§9). Ele
/// responde do próprio SQLite, então o app enxerga exatamente a mesma verdade
/// que o caixa — inclusive com a internet da loja caída. O caminho antigo caía
/// para a nuvem quando o principal não respondia, e era justamente aí que o
/// garçom via uma comanda desatualizada: a nuvem não conhecia os pedidos
/// lançados desde a queda, e um item lançado sobre esse retrato ia parar no
/// pedido errado. Sem principal, a leitura falha com o motivo na tela.
class OrdersRepository {
  OrdersRepository({
    required this.principalClient,
    required this.gateway,
    required this.session,
    required this.principal,
    PrincipalCache? cache,
    OrderDrafts? drafts,
  }) : cache = cache ?? PrincipalCache(),
       drafts = drafts ?? OrderDrafts();

  final PrincipalClient principalClient;

  /// Cópia local das últimas leituras confirmadas pelo principal. É o que
  /// mantém o salão trabalhando quando o caixa cai (§9).
  final PrincipalCache cache;

  /// De onde veio a última leitura: do Caixa Principal ou da cópia local.
  ///
  /// A tela consulta logo depois de aguardar a chamada, no mesmo passo — a
  /// interface é uma linha de execução só, então não há leitura de outra tela
  /// no meio. Existe para o garçom saber que está olhando um retrato, e de
  /// quando ele é.
  ReadOrigin lastReadOrigin = const ReadOrigin.live();
  final RelayGateway gateway;

  /// Itens escolhidos e ainda não enviados, por pedido. Eles saem juntos
  /// quando o garçom confirma o envio — que é quando a comanda é impressa.
  final OrderDrafts drafts;

  final WaiterSession session;

  /// Pareamento do aparelho — do dispositivo, não do garçom (ver
  /// `SessionStorage`).
  final PrincipalConfig principal;

  /// Página pequena de propósito: o aparelho é um celular no meio do salão,
  /// muitas vezes no limite do Wi-Fi. Mais páginas curtas respondem melhor do
  /// que uma longa que trava a tela.
  static const _pageSize = 30;

  /// O que "em atendimento" quer dizer para o salão.
  ///
  /// São DOIS estados, não um. `awaiting_payment` é a conta fechada e ainda não
  /// recebida — a mesa continua ocupada, o cliente continua sentado e o garçom
  /// continua atendendo. Pedir só `open` fazia a comanda sumir da lista no
  /// instante em que alguém fechava a conta, e ela só reaparecia por um
  /// caminho torto: "novo pedido → comanda", porque o backend procura o pedido
  /// existente da comanda nos dois estados
  /// (`OrderViewSet.by_command`, `status__in=[open, awaiting_payment]`).
  ///
  /// É a mesma dupla que o PDV desktop considera aberta
  /// (`home_page_orders.dart`), então caixa e salão passam a enxergar a mesma
  /// lista.
  static const _openStatuses = ['open', 'awaiting_payment'];

  /// Pedidos em aberto do restaurante do garçom.
  ///
  /// Uma consulta por estado, e não uma só: o filtro `status` é de igualdade
  /// exata tanto no DRF quanto no SQLite local que o Caixa Principal usa para
  /// responder — não existe `status__in` para o app pedir. Duas consultas
  /// curtas na rede da loja custam menos do que baixar a lista inteira sem
  /// filtro e separar aqui.
  Future<List<Map<String, dynamic>>> openOrders() async {
    final merged = <String, Map<String, dynamic>>{};
    var origin = const ReadOrigin.live();
    for (final status in _openStatuses) {
      final page = await _read(
        '/orders/',
        query: {
          'status': status,
          'restaurant': session.user.restaurantId,
          'ordering': '-opened_at',
          'page_size': 50,
        },
      );
      // A origem mais pessimista manda: se QUALQUER uma das duas veio da cópia
      // local, a lista inteira é um retrato e a faixa de aviso precisa
      // aparecer. Sem isto, a segunda leitura (viva) apagaria o aviso da
      // primeira (de cache) e o garçom lançaria item sobre dado velho sem
      // saber.
      if (lastReadOrigin.fromCache) origin = lastReadOrigin;
      for (final order in _rows(page)) {
        merged['${order['id']}'] = order;
      }
    }
    lastReadOrigin = origin;
    final orders = merged.values.toList();
    // O `-opened_at` de cada consulta ordena só a sua metade; juntas, elas
    // voltariam com os `awaiting_payment` todos depois dos `open`.
    orders.sort(
      (a, b) => '${b['opened_at'] ?? ''}'.compareTo('${a['opened_at'] ?? ''}'),
    );
    return orders;
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

  /// Formas de pagamento ativas do restaurante, servidas pelo Caixa Principal.
  Future<List<Map<String, dynamic>>> paymentMethods() async {
    final page = await _read(
      '/payments/methods/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'page_size': 100,
      },
    );
    return _rows(page);
  }

  /// Recebimentos já registrados no pedido.
  Future<List<Map<String, dynamic>>> payments(String orderId) async {
    final page = await _read('/orders/$orderId/payments/');
    return _rows(page);
  }

  /// Sessão de caixa aberta, quando existe.
  ///
  /// Um recebimento em dinheiro precisa entrar em algum caixa: é o principal
  /// quem sabe qual está aberto. Devolve `null` quando não há nenhum — o
  /// aparelho continua podendo receber nas outras formas.
  Future<Map<String, dynamic>?> currentCashRegister() async {
    try {
      final response = await _read(
        '/cash-register/current/',
        query: {'restaurant': session.user.restaurantId},
      );
      final id = '${response['id'] ?? ''}';
      // Um caixa "aberto" segundo uma cópia velha pode já ter sido fechado.
      // Aceitar isso autorizaria um recebimento em dinheiro numa sessão que
      // não existe mais — melhor recusar a forma dinheiro do que registrar
      // numa sessão errada.
      if (id.isEmpty || response['_from_cache'] == true) return null;
      return response;
    } on ApiException {
      return null;
    } on PrincipalUnavailable {
      return null;
    }
  }

  /// Fecha a conta: aplica taxa de serviço e desconto e trava novos itens.
  ///
  /// Entra na fila se o caixa estiver fora do ar — o fechamento é uma decisão
  /// do atendimento, não uma operação que precise do servidor na hora.
  Future<Map<String, dynamic>> closeOrder({
    required String orderId,
    bool serviceFeeEnabled = true,
    String discount = '0',
  }) => _mutate(
    method: 'POST',
    path: '/orders/$orderId/close/',
    kind: 'close_order',
    summary: 'Fechar a conta',
    body: {'service_fee_enabled': serviceFeeEnabled, 'discount': discount},
  );

  /// Registra um recebimento.
  ///
  /// O identificador do pagamento nasce aqui, antes de qualquer chamada: é ele
  /// que o backend usa para deduplicar. Um reenvio depois de um timeout
  /// devolve o mesmo recebimento em vez de cobrar duas vezes.
  Future<Map<String, dynamic>> pay({
    required String orderId,
    required String paymentMethodId,
    required String amount,
    String? cashRegisterId,
    String reference = '',
  }) => _mutate(
    method: 'POST',
    path: '/orders/$orderId/pay/',
    kind: 'pay_order',
    summary: 'Receber $amount',
    body: {
      'payment_method': paymentMethodId,
      'amount': amount,
      'cash_register': ?cashRegisterId,
      'client_payment_id': 'offline-${RelaySignature.randomId()}',
      'metadata': {'reference': reference, 'source': 'flutter_garcom'},
    },
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

  /// Lê pelo Caixa Principal e guarda o resultado.
  ///
  /// Com o principal fora do ar, devolve a última resposta confirmada, marcada
  /// com `_from_cache` e a idade — a tela avisa que o dado pode ter mudado. É
  /// deliberadamente uma cópia velha e assumida, não um palpite: um pedido
  /// aberto em outro terminal depois da queda não aparece aqui, e o garçom
  /// precisa saber disso antes de lançar item em cima.
  Future<Map<String, dynamic>> _read(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    final key = PrincipalCache.keyFor(path, query);
    try {
      final fresh = await principalClient.read(
        principal,
        session.identity,
        path: path,
        query: query,
      );
      await cache.write(key, fresh);
      lastReadOrigin = const ReadOrigin.live();
      return fresh;
    } on PrincipalUnavailable {
      final cached = await cache.read(key);
      if (cached == null) rethrow;
      lastReadOrigin = ReadOrigin.cached(cached.updatedAt);
      return {
        ...cached.payload,
        '_from_cache': true,
        '_cached_at': cached.updatedAt.toIso8601String(),
        '_cache_stale': cached.age > PrincipalCache.staleAfter,
      };
    }
  }

  /// Quando foi a última vez que este aparelho falou com o Caixa Principal.
  Future<DateTime?> lastSyncedAt() => cache.newestUpdatedAt();

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

/// De onde veio a última leitura servida ao aplicativo.
class ReadOrigin {
  const ReadOrigin.live() : fromCache = false, at = null;
  const ReadOrigin.cached(DateTime this.at) : fromCache = true;

  /// A resposta veio da cópia local, porque o Caixa Principal não respondeu.
  final bool fromCache;

  /// Quando o Caixa Principal confirmou esse dado pela última vez.
  final DateTime? at;

  /// Velho o bastante para o salão ter mudado de verdade nesse meio-tempo.
  bool get stale =>
      at != null && DateTime.now().difference(at!) > PrincipalCache.staleAfter;
}
