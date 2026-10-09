import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/read_cache.dart';
import '../../../core/network/resource_page.dart';
import '../../../core/sync/backend_gateway.dart';
import '../../../core/sync/operation_id.dart';
import '../../auth/domain/waiter_session.dart';
import '../domain/operator_code_keeper.dart';
import 'order_drafts.dart';
import 'order_subject.dart';

export '../../../core/network/resource_page.dart';
export '../domain/operator_code_keeper.dart';
export 'order_subject.dart';

part 'orders_command_items.dart';
part 'orders_commands.dart';
part 'orders_customers.dart';
part 'orders_queries.dart';
part 'orders_subject_api.dart';

class OrdersRepository {
  OrdersRepository({
    required this.api,
    required this.gateway,
    required this.session,
    OrderDrafts? drafts,
    OperatorCodeKeeper? operatorCodes,
    this.onPrintJobsCreated,
    this.exigeCodigoAgora,
    this.catalogCache,
    this.perguntarMesa,
  }) : drafts = drafts ?? OrderDrafts(),
       operatorCodes = operatorCodes ?? OperatorCodeKeeper();

  final ApiClient api;
  final BackendGateway gateway;
  final WaiterSession session;
  final OrderDrafts drafts;
  final void Function()? onPrintJobsCreated;

  /// Cardápio e formas de pagamento abrem com a última cópia (ver
  /// [ReadCache]). Mora no app, e não aqui: este repositório é recriado a
  /// cada redesenho da tela inicial.
  final ReadCache? catalogCache;

  /// A configuração "Perguntar mesa" deste aparelho (lida na hora: o garçom
  /// pode trocar pelo menu com a tela aberta).
  final bool Function()? perguntarMesa;
  bool get askTable => perguntarMesa?.call() ?? true;

  /// A exigência ATUAL da sessão. A tela de pedidos guarda este repositório
  /// desde que abriu; ler de `session` aqui devolveria o valor do momento do
  /// login, e não o que o servidor disse ao reler o usuário.
  final bool Function()? exigeCodigoAgora;

  /// O código de quem está lançando, por atendimento.
  ///
  /// MORA AQUI, e não dentro de cada apresentador, porque o código é
  /// informado numa tela (o fluxo de abrir o atendimento) e usado em outra (o
  /// detalhe). Com um guardião por apresentador, o garçom digitava o código
  /// para o primeiro item e era perguntado de novo no segundo.
  final OperatorCodeKeeper operatorCodes;

  /// Este restaurante exige o código antes do lançamento?
  ///
  /// Vem da SESSÃO, e não de uma consulta ao cadastro: a resposta é
  /// necessária antes do primeiro item, num aparelho que lança offline.
  bool get requiresOperatorCode =>
      exigeCodigoAgora?.call() ?? session.user.requireOperatorCode;
  ReadOrigin lastReadOrigin = const ReadOrigin.live();
  DateTime? _lastSyncedAt;

  Future<Map<String, dynamic>> refreshPrintingAfter(
    Future<Map<String, dynamic>> operation,
  ) async {
    final result = await operation;
    onPrintJobsCreated?.call();
    return result;
  }

  Future<Map<String, dynamic>> read(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    final response = await api.get(path, query: query);
    _lastSyncedAt = DateTime.now();
    lastReadOrigin = const ReadOrigin.live();
    return response;
  }

  /// Leitura de CATÁLOGO: com cache, a cópia recente aparece na hora.
  ///
  /// A chave leva usuário e restaurante: outra sessão no mesmo aparelho nunca
  /// vê a lista desta. Sem cache configurado, é uma leitura comum.
  Future<Map<String, dynamic>> readCatalog(
    String path, {
    Map<String, dynamic>? query,
  }) {
    final cache = catalogCache;
    if (cache == null) return read(path, query: query);
    final params =
        (query ?? const <String, dynamic>{}).entries
            .map((entry) => '${entry.key}=${entry.value}')
            .toList()
          ..sort();
    final key =
        '${session.user.id}|${session.user.restaurantId}|$path?${params.join('&')}';
    return cache.read(key, () => read(path, query: query));
  }

  Future<Map<String, dynamic>> mutate({
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

  Future<DateTime?> lastSyncedAt() async => _lastSyncedAt;
}

class ReadOrigin {
  const ReadOrigin.live() : fromCache = false, at = null;
  const ReadOrigin.cached(this.at) : fromCache = true;

  final bool fromCache;
  final DateTime? at;
  bool get stale => false;
}

List<Map<String, dynamic>> _rows(Map<String, dynamic> page) {
  final results = page['results'] ?? page['data'];
  if (results is! List) return const [];
  return results
      .whereType<Map>()
      .map(Map<String, dynamic>.from)
      .toList(growable: false);
}
