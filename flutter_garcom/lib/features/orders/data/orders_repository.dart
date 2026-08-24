import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/relay/principal_client.dart';
import '../../../core/relay/relay_signature.dart';
import '../../auth/domain/waiter_session.dart';

/// Pedidos do salão, sempre pela ótica do Caixa Principal.
///
/// **Escrita**: exclusivamente pelo relay. O principal grava, imprime na
/// impressora do balcão e sincroniza com a nuvem. Se ele estiver fora do ar, o
/// lançamento falha na hora e o garçom sabe — bem melhor do que um pedido
/// aceito no celular que a cozinha nunca recebeu.
///
/// **Leitura**: tenta o principal primeiro (é a mesma verdade que o caixa
/// enxerga, e funciona com a internet da loja caída) e cai para o backend
/// quando o principal não responde — assim consultar um pedido continua
/// possível mesmo com o caixa desligado.
class OrdersRepository {
  OrdersRepository({
    required this.api,
    required this.principalClient,
    required this.session,
    required this.principal,
  });

  final ApiClient api;
  final PrincipalClient principalClient;
  final WaiterSession session;

  /// Pareamento do aparelho — do dispositivo, não do garçom (ver
  /// `SessionStorage`).
  final PrincipalConfig principal;

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

  /// Mesas do restaurante, para abrir um pedido novo.
  Future<List<Map<String, dynamic>>> tables() async {
    final page = await _read(
      '/tables/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'page_size': 200,
        'ordering': 'number',
      },
    );
    return _rows(page);
  }

  /// Catálogo vendável. `page_size` alto de propósito: o garçom precisa
  /// buscar o produto na hora, e paginar no meio do atendimento atrasa a mesa.
  Future<List<Map<String, dynamic>>> products() async {
    final page = await _read(
      '/menu/products/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'page_size': 300,
        'ordering': 'name',
      },
    );
    return _rows(page);
  }

  Future<Map<String, dynamic>> openTableOrder(String tableId) => _mutate(
    method: 'POST',
    path: '/orders/open-table/',
    body: {'table': tableId},
  );

  Future<Map<String, dynamic>> addItem({
    required String orderId,
    required String productId,
    required int quantity,
    String customerNote = '',
    List<String> addonIds = const [],
    String? variationId,
  }) => _mutate(
    method: 'POST',
    path: '/orders/$orderId/items/',
    body: {
      'product': productId,
      'quantity': quantity,
      'variations': variationId == null ? const [] : [variationId],
      'addons': addonIds,
      'customer_note': customerNote,
    },
  );

  Future<Map<String, dynamic>> voidItem({
    required String orderId,
    required String itemId,
    required String reason,
  }) => _mutate(
    method: 'DELETE',
    path: '/orders/$orderId/items/$itemId/void/',
    body: {'reason': reason},
  );

  /// Manda para a cozinha — é aqui que o principal imprime.
  Future<Map<String, dynamic>> sendToKitchen(String orderId) =>
      _mutate(method: 'POST', path: '/orders/$orderId/send-to-kitchen/');

  Future<Map<String, dynamic>> _mutate({
    required String method,
    required String path,
    Map<String, dynamic>? body,
  }) => principalClient.mutate(
    principal,
    session.identity,
    method: method,
    path: path,
    // Um id por tentativa de operação: se a resposta se perder, o app pode
    // repetir a MESMA operação e o principal devolve o recibo guardado em vez
    // de lançar o item duas vezes.
    operationId: RelaySignature.randomId(),
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
