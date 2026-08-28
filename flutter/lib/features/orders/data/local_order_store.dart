import '../../../core/data/local_id.dart';
import '../../../core/data/order_repository.dart';
import '../../../core/network/api_client.dart';

/// Acesso da tela de pedidos ao armazenamento operacional local.
///
/// Antes esta classe era um segundo banco SQLite (`local_orders.sqlite`) com o
/// seu próprio esquema e a sua própria cópia das regras de total. Duas bases
/// para o mesmo dado significavam duas verdades: o cache HTTP conhecia uma
/// versão do pedido, este arquivo conhecia outra, e a fila de sincronização
/// uma terceira.
///
/// Agora é apenas a porta de entrada da tela para o [OrderRepository] — que
/// grava no banco único do Caixa Principal (§1, §27). A assinatura foi
/// preservada de propósito: as telas continuam chamando os mesmos métodos,
/// sem saber que a implementação embaixo mudou.
class LocalOrderStore {
  LocalOrderStore({required this.api});

  final ApiClient api;

  OrderRepository? get _repository => api.localStore?.orders;

  /// Guarda a versão vinda do servidor preservando o que ainda não subiu.
  Future<Map<String, dynamic>> saveFromServer(
    Map<String, dynamic> order, {
    required String scope,
  }) async {
    final repository = _repository;
    if (repository == null) return order;
    final record = await repository.applyRemote(order);
    if (record != null) return record.toApiJson();
    // Havia alteração local pendente: ela vale mais que a cópia do servidor,
    // porque é o que o operador acabou de lançar e ainda está na fila.
    final stored = await repository.read('${order['id'] ?? ''}');
    return stored?.toApiJson() ?? order;
  }

  Future<void> saveAllFromServer(
    List<Map<String, dynamic>> orders, {
    required String scope,
  }) async {
    final repository = _repository;
    if (repository == null) return;
    await repository.applyRemoteList(orders);
  }

  Future<Map<String, dynamic>?> read(
    String orderId, {
    required String scope,
  }) async {
    final record = await _repository?.read(orderId);
    return record?.toApiJson();
  }

  /// Pedidos guardados, do mais recente para o mais antigo.
  Future<List<Map<String, dynamic>>> recent({
    required String scope,
    int limit = 50,
  }) async {
    final repository = _repository;
    if (repository == null) return const [];
    final page = await repository.list(query: {'page': 1, 'page_size': limit});
    return page.results;
  }

  /// Troca o ID temporário pelo real depois que a fila sincroniza.
  Future<void> replaceId(
    String temporaryId,
    String realId, {
    required String scope,
  }) async {
    if (!LocalId.isTemporary(temporaryId)) return;
    await _repository?.replaceId(temporaryId, realId);
  }

  Future<void> remove(String orderId, {required String scope}) async {
    await _repository?.markRemoteDeleted(orderId);
  }

  /// O banco pertence ao runtime do PDV, não a esta tela.
  Future<void> close() async {}
}
