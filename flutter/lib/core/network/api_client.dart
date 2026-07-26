import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_exception.dart';
import 'offline_store.dart';

class ApiClient {
  ApiClient({
    required this.baseUrl,
    http.Client? client,
    OfflineStore? offlineStore,
  }) : _client = client ?? http.Client(),
       _offlineStore = offlineStore ?? OfflineStore() {
    _retryTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => unawaited(_flushPending()),
    );
  }

  final String baseUrl;
  final http.Client _client;
  final OfflineStore _offlineStore;
  Timer? _retryTimer;
  String? _lastAccessToken;
  bool _syncing = false;
  final _connectivityController = StreamController<bool>.broadcast();
  static const requestTimeout = Duration(seconds: 20);

  Stream<bool> get connectivityChanges => _connectivityController.stream;

  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, dynamic>? query,
    String? accessToken,
  }) => _request('GET', path, query: query, accessToken: accessToken);

  Future<Map<String, dynamic>> post(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
  }) => _request('POST', path, body: body, accessToken: accessToken);

  Future<Map<String, dynamic>> patch(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
  }) => _request('PATCH', path, body: body, accessToken: accessToken);

  Future<Map<String, dynamic>> delete(
    String path, {
    Map<String, dynamic>? body,
    String? accessToken,
  }) => _request('DELETE', path, body: body, accessToken: accessToken);

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
  }) async {
    if (accessToken != null) _lastAccessToken = accessToken;
    final cacheKey = _cacheKey(path, query, accessToken);
    try {
      final decoded = await _requestOnline(
        method,
        path,
        query: query,
        body: body,
        accessToken: accessToken,
      );
      _connectivityController.add(true);
      if (method == 'GET' && _canCache(path)) {
        await _offlineStore.cache(cacheKey, decoded);
      }
      unawaited(_flushPending());
      return decoded;
    } on _NetworkUnavailable {
      _connectivityController.add(false);
      if (method == 'GET' && _canCache(path)) {
        final cached = await _offlineStore.cached(cacheKey);
        if (cached != null) return {...cached, '_offline_cache': true};
      }
      if (method != 'GET' && _canQueue(path)) {
        return _queueMutation(
          method: method,
          path: path,
          query: query,
          body: body,
        );
      }
      throw const ApiException(
        'Sem conexão e não há dados offline disponíveis para esta operação.',
      );
    }
  }

  Future<Map<String, dynamic>> _requestOnline(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
  }) async {
    try {
      final uri = Uri.parse('$baseUrl$path').replace(
        queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
      );
      final request = http.Request(method, uri)
        ..headers.addAll({
          'Content-Type': 'application/json',
          if (accessToken != null) 'Authorization': 'Bearer $accessToken',
        });
      if (body != null) request.body = jsonEncode(body);
      final streamed = await _client.send(request).timeout(requestTimeout);
      final response = await http.Response.fromStream(streamed);
      final raw = response.body.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(utf8.decode(response.bodyBytes));
      final decoded = raw is List
          ? <String, dynamic>{'results': raw}
          : (raw as Map<String, dynamic>);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        if (response.statusCode >= 500) throw const _NetworkUnavailable();
        throw ApiException(
          _messageFor(response.statusCode, decoded),
          statusCode: response.statusCode,
        );
      }
      return decoded;
    } on ApiException {
      rethrow;
    } on FormatException {
      throw const ApiException('A API retornou uma resposta inválida.');
    } on TimeoutException {
      throw const _NetworkUnavailable();
    } on SocketException {
      throw const _NetworkUnavailable();
    } on http.ClientException {
      throw const _NetworkUnavailable();
    }
  }

  Future<Map<String, dynamic>> _queueMutation({
    required String method,
    required String path,
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
  }) async {
    final now = DateTime.now().microsecondsSinceEpoch;
    final queueId = 'queue-$now';
    final temporaryId = method == 'POST' ? 'offline-$now' : null;
    final optimistic = <String, dynamic>{
      ...?body,
      'id': ?temporaryId,
      '_offline_pending': true,
      '_offline_queue_id': queueId,
    };
    await _offlineStore.enqueue({
      'queue_id': queueId,
      'method': method,
      'path': path,
      'query': query,
      'body': body,
      'temporary_id': temporaryId,
      'created_at': DateTime.now().toIso8601String(),
    });
    await _offlineStore.applyOptimistic(
      path: path,
      method: method,
      value: optimistic,
    );
    return optimistic;
  }

  Future<void> _flushPending() async {
    final token = _lastAccessToken;
    if (_syncing || token == null) return;
    _syncing = true;
    try {
      final pending = await _offlineStore.pending();
      for (final item in pending) {
        try {
          final response = await _requestOnline(
            '${item['method']}',
            '${item['path']}',
            query: item['query'] is Map
                ? Map<String, dynamic>.from(item['query'] as Map)
                : null,
            body: item['body'] is Map
                ? Map<String, dynamic>.from(item['body'] as Map)
                : null,
            accessToken: token,
          );
          final temporaryId = '${item['temporary_id'] ?? ''}';
          final realId = '${response['id'] ?? ''}';
          if (temporaryId.isNotEmpty && realId.isNotEmpty) {
            await _offlineStore.replaceTemporaryId(temporaryId, realId);
          }
          await _offlineStore.remove('${item['queue_id']}');
          _connectivityController.add(true);
        } on _NetworkUnavailable {
          _connectivityController.add(false);
          break;
        } on ApiException {
          // Erro de negocio: preserva a operacao e a ordem para revisao.
          break;
        }
      }
    } finally {
      _syncing = false;
    }
  }

  bool _canCache(String path) =>
      !path.startsWith('/auth/') && !path.contains('/cash-auth/');

  bool _canQueue(String path) {
    if (path.startsWith('/auth/')) return false;
    return ![
      'claim-agent',
      'release-agent',
      'latest-reading',
      '/scales/readings/',
      'mark-printed',
      'mark-failed',
      'test-connection',
      '/print/',
    ].any(path.contains);
  }

  String _cacheKey(String path, Map<String, dynamic>? query, String? token) {
    final sorted = (query?.entries.toList() ?? [])
      ..sort((a, b) => a.key.compareTo(b.key));
    return '${_tokenScope(token)}|$path|'
        '${sorted.map((entry) => '${entry.key}=${entry.value}').join('&')}';
  }

  String _tokenScope(String? token) {
    if (token == null) return 'public';
    try {
      final parts = token.split('.');
      final payload = jsonDecode(
        utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))),
      );
      if (payload is Map) {
        return '${payload['account_id'] ?? payload['user_id'] ?? payload['sub'] ?? 'authenticated'}';
      }
    } catch (_) {}
    return 'authenticated';
  }

  String _messageFor(int status, Map<String, dynamic> body) {
    final detail = body['detail'];
    if (detail is String && detail.isNotEmpty) return detail;
    if (detail is List && detail.isNotEmpty) return detail.join(' ');
    final messages = _validationMessages(body);
    if (messages.isNotEmpty) return messages.join('\n');
    if (status == 401) return 'Usuário ou senha inválidos.';
    if (status == 403) {
      return 'Você não tem permissão para realizar esta operação.';
    }
    return 'Não foi possível concluir a solicitação.';
  }

  List<String> _validationMessages(Object? value, [String? field]) {
    if (value == null) return const [];
    if (value is String) {
      final text = value.trim();
      if (text.isEmpty) return const [];
      return [field == null ? text : '${_fieldLabel(field)}: $text'];
    }
    if (value is List) {
      return value.expand((item) => _validationMessages(item, field)).toList();
    }
    if (value is Map) {
      return value.entries
          .where(
            (entry) =>
                !{'success', 'status_code', 'code'}.contains('${entry.key}'),
          )
          .expand(
            (entry) => _validationMessages(
              entry.value,
              '${entry.key}' == 'errors' || '${entry.key}' == 'non_field_errors'
                  ? null
                  : '${entry.key}',
            ),
          )
          .toList();
    }
    return [field == null ? '$value' : '${_fieldLabel(field)}: $value'];
  }

  String _fieldLabel(String field) =>
      const {
        'amount': 'Valor',
        'payment_method': 'Forma de pagamento',
        'discount': 'Desconto',
        'quantity': 'Quantidade',
        'table': 'Mesa',
        'cash_station': 'Caixa',
        'operators': 'Operadores',
        'name': 'Nome',
      }[field] ??
      field.replaceAll('_', ' ');

  void dispose() {
    _retryTimer?.cancel();
    _client.close();
    _connectivityController.close();
  }

  Future<void> syncPendingNow() => _flushPending();

  Future<int> pendingOperations() async =>
      (await _offlineStore.pending()).length;
}

class _NetworkUnavailable implements Exception {
  const _NetworkUnavailable();
}
