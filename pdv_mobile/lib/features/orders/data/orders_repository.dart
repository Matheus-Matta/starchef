import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/resource_page.dart';
import '../../../core/sync/backend_gateway.dart';
import '../../../core/sync/operation_id.dart';
import '../../auth/domain/waiter_session.dart';
import 'order_drafts.dart';

export '../../../core/network/resource_page.dart';

part 'orders_commands.dart';
part 'orders_queries.dart';

class OrdersRepository {
  OrdersRepository({
    required this.api,
    required this.gateway,
    required this.session,
    OrderDrafts? drafts,
  }) : drafts = drafts ?? OrderDrafts();

  final ApiClient api;
  final BackendGateway gateway;
  final WaiterSession session;
  final OrderDrafts drafts;
  ReadOrigin lastReadOrigin = const ReadOrigin.live();
  DateTime? _lastSyncedAt;

  Future<Map<String, dynamic>> read(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    final response = await api.get(path, query: query);
    _lastSyncedAt = DateTime.now();
    lastReadOrigin = const ReadOrigin.live();
    return response;
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
