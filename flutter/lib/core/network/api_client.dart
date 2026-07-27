import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;

import 'api_exception.dart';
import 'mutation_relay.dart';
import 'offline_store.dart';

enum NetworkSyncPhase { unknown, online, offline, syncing, degraded, blocked }

class NetworkSyncStatus {
  const NetworkSyncStatus({
    required this.phase,
    this.pending = 0,
    this.retrying = 0,
    this.blocked = 0,
    this.lastError,
    this.nextRetryAt,
  });

  final NetworkSyncPhase phase;
  final int pending;
  final int retrying;
  final int blocked;
  final String? lastError;
  final DateTime? nextRetryAt;

  int get total => pending + retrying + blocked;
  bool get hasConnection =>
      phase == NetworkSyncPhase.online ||
      phase == NetworkSyncPhase.syncing ||
      phase == NetworkSyncPhase.blocked;

  @override
  bool operator ==(Object other) =>
      other is NetworkSyncStatus &&
      phase == other.phase &&
      pending == other.pending &&
      retrying == other.retrying &&
      blocked == other.blocked &&
      lastError == other.lastError &&
      nextRetryAt == other.nextRetryAt;

  @override
  int get hashCode =>
      Object.hash(phase, pending, retrying, blocked, lastError, nextRetryAt);
}

class ApiClient {
  ApiClient({
    required this.baseUrl,
    http.Client? client,
    OfflineStore? offlineStore,
    this.requestTimeout = const Duration(seconds: 20),
  }) : _client = client ?? http.Client(),
       _offlineStore = offlineStore ?? OfflineStore();

  static const _flushDebounce = Duration(milliseconds: 450);
  static const _baseRetryDelay = Duration(seconds: 2);
  static const _maxRetryDelay = Duration(minutes: 2);
  static const _maxOperationsPerCycle = 20;

  final String baseUrl;
  final http.Client _client;
  final OfflineStore _offlineStore;
  final Duration requestTimeout;
  final _connectivityController = StreamController<bool>.broadcast();
  final _syncStatusController = StreamController<NetworkSyncStatus>.broadcast();

  Timer? _retryTimer;
  Timer? _debounceTimer;
  String? _lastAccessToken;
  String? _activeScope;
  bool _syncing = false;
  bool _disposed = false;
  int _retryAttempt = 0;
  int _operationSequence = 0;
  final Random _secureRandom = Random.secure();
  final String _leaseOwner = _newLeaseOwner();
  bool? _lastConnectivityValue;
  NetworkSyncStatus _syncStatus = const NetworkSyncStatus(
    phase: NetworkSyncPhase.unknown,
  );
  MutationRelay? _mutationRelay;

  Stream<bool> get connectivityChanges => _connectivityController.stream;
  Stream<NetworkSyncStatus> get syncStatusChanges =>
      _syncStatusController.stream;
  NetworkSyncStatus get syncStatus => _syncStatus;

  void attachMutationRelay(MutationRelay? relay) {
    _mutationRelay = relay;
  }

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
    _rememberSession(accessToken);
    final cacheKey = _cacheKey(path, query, accessToken);
    final operationId = method == 'GET' ? null : _nextOperationId();
    final queueableMutation =
        method != 'GET' && _canQueue(method, path, body);
    if (method != 'GET' && _containsPrincipalTemporaryId(path, query, body)) {
      final relay = _mutationRelay;
      if (relay == null || !queueableMutation) {
        throw ApiException(
          'Esta operação pertence ao Caixa Principal, que não está '
          'disponível nesta estação.',
        );
      }
      try {
        return await _relayMutation(
          relay,
          method: method,
          path: path,
          operationId: operationId!,
          query: query,
          body: body,
        );
      } on MutationRelayUnavailable catch (error) {
        throw ApiException(
          'O Caixa Principal precisa concluir esta operação. ${error.message}',
        );
      } on MutationRelayUncertain catch (error) {
        throw ApiException(error.message);
      }
    }

    // In client mode, eligible sales are handed to the principal before any
    // cloud request starts. Falling back from a timed-out cloud request to the
    // LAN would be ambiguous when the backend committed but its response was
    // lost. A definitively unavailable principal may still fall through to
    // the cloud and, if needed, to this station's own outbox.
    var relayWasUnavailable = false;
    final preferredRelay = _mutationRelay;
    if (queueableMutation && preferredRelay != null) {
      try {
        return await _relayMutation(
          preferredRelay,
          method: method,
          path: path,
          operationId: operationId!,
          query: query,
          body: body,
        );
      } on MutationRelayUnavailable {
        relayWasUnavailable = true;
      } on MutationRelayUncertain catch (error) {
        throw ApiException(error.message);
      }
    }

    try {
      final decoded = await _requestOnline(
        method,
        path,
        query: query,
        body: body,
        accessToken: accessToken,
        operationId: operationId,
      );
      _retryAttempt = 0;
      await _publishStatus(NetworkSyncPhase.online);
      if (method == 'GET' && _canCache(path)) {
        await _offlineStore.cache(cacheKey, decoded);
      }
      _scheduleFlush();
      return decoded;
    } on _NetworkUnavailable catch (error) {
      final phase = error.isOffline
          ? NetworkSyncPhase.offline
          : NetworkSyncPhase.degraded;
      await _publishStatus(phase, error: error.message);

      if (method == 'GET' && _canCache(path)) {
        final cached = await _offlineStore.cached(cacheKey);
        if (cached != null) {
          _scheduleRetry(serverDelay: error.retryAfter);
          return {...cached, '_offline_cache': true};
        }
      }
      if (method != 'GET' && _canQueue(method, path, body)) {
        final relay = _mutationRelay;
        if (relay != null && !relayWasUnavailable) {
          try {
            return await _relayMutation(
              relay,
              method: method,
              path: path,
              operationId: operationId!,
              query: query,
              body: body,
            );
          } on MutationRelayUnavailable {
            // A entrega não começou; a outbox desta estação é um fallback seguro.
          } on MutationRelayUncertain catch (relayError) {
            throw ApiException(relayError.message);
          }
        }
        final queued = await _queueMutation(
          method: method,
          path: path,
          query: query,
          body: body,
          operationId: operationId!,
          accessToken: accessToken,
          failurePhase: phase,
        );
        _scheduleRetry(serverDelay: error.retryAfter);
        return queued;
      }
      _scheduleRetry(serverDelay: error.retryAfter);
      throw ApiException(
        _requiresOnline(path)
            ? 'Esta operação exige conexão com o servidor. ${error.message}'
            : error.message,
      );
    }
  }

  Future<Map<String, dynamic>> _requestOnline(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    String? operationId,
  }) async {
    try {
      final uri = Uri.parse('$baseUrl$path').replace(
        queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
      );
      final headers = <String, String>{'Content-Type': 'application/json'};
      if (accessToken != null) {
        headers['Authorization'] = 'Bearer $accessToken';
      }
      if (operationId != null) headers['Idempotency-Key'] = operationId;
      final request = http.Request(method, uri)..headers.addAll(headers);
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
        final error = ApiException(
          _messageFor(response.statusCode, decoded),
          statusCode: response.statusCode,
        );
        if (_isRetryableStatus(response.statusCode)) {
          throw _NetworkUnavailable(
            error.message,
            isOffline: false,
            retryAfter: _retryAfter(response.headers['retry-after']),
          );
        }
        throw error;
      }
      return decoded;
    } on ApiException {
      rethrow;
    } on _NetworkUnavailable {
      rethrow;
    } on FormatException {
      throw ApiException(
        'A API retornou uma resposta inválida. Servidor configurado: $baseUrl.',
      );
    } on TimeoutException {
      throw _NetworkUnavailable(
        'O servidor demorou mais de ${requestTimeout.inSeconds} segundos para responder.',
      );
    } on SocketException catch (error) {
      throw _NetworkUnavailable(
        'Não foi possível conectar ao servidor '
        '${error.address?.address ?? Uri.tryParse(baseUrl)?.host ?? baseUrl}.',
      );
    } on http.ClientException catch (error) {
      throw _NetworkUnavailable(
        'Não foi possível acessar a API em $baseUrl: ${error.message}',
      );
    }
  }

  Future<Map<String, dynamic>> _queueMutation({
    required String method,
    required String path,
    required String operationId,
    required String? accessToken,
    required NetworkSyncPhase failurePhase,
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String temporaryIdPrefix = 'offline-',
  }) async {
    final scope = _outboxScope(accessToken);
    final createsResource = _createsResource(method, path);
    final temporaryId = createsResource
        ? '$temporaryIdPrefix$operationId'
        : null;
    final optimistic = <String, dynamic>{
      ...?body,
      'id': ?temporaryId,
      '_offline_pending': true,
      '_offline_queue_id': operationId,
      '_offline_operation': path,
    };
    await _offlineStore.enqueue({
      'queue_id': operationId,
      'scope': scope,
      'method': method,
      'path': path,
      'query': query,
      'body': body,
      'temporary_id': temporaryId,
      'idempotency_key': operationId,
      'created_at': DateTime.now().toUtc().toIso8601String(),
    });
    await _offlineStore.applyOptimistic(
      path: path,
      method: method,
      value: optimistic,
      cacheScope: _cacheNamespace(accessToken),
    );
    await _publishStatus(failurePhase, error: 'Operação salva localmente.');
    return optimistic;
  }

  Future<Map<String, dynamic>> _relayMutation(
    MutationRelay relay, {
    required String method,
    required String path,
    required String operationId,
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
  }) async {
    final response = await relay.relay(
      RelayMutation(
        method: method,
        path: path,
        operationId: operationId,
        query: query,
        body: body,
      ),
    );
    return {...response, '_relayed_to_principal': true};
  }

  /// Accepts one authenticated LAN mutation on the principal checkout.
  ///
  /// Only the same conservative allowlist used by the local outbox is exposed.
  /// Dependent operations carrying a principal temporary ID are queued without
  /// first sending an invalid temporary reference to the cloud.
  Future<Map<String, dynamic>> acceptRelayedMutation(
    RelayMutation mutation, {
    required String accessToken,
  }) async {
    if (!_canQueue(mutation.method, mutation.path, mutation.body)) {
      throw ApiException(
        'Operação não autorizada no relay local.',
        statusCode: 400,
      );
    }
    _rememberSession(accessToken);
    final scope = _outboxScope(accessToken);
    if (_containsPrincipalTemporaryId(
      mutation.path,
      mutation.query,
      mutation.body,
    )) {
      final queued = await _queueMutation(
        method: mutation.method,
        path: mutation.path,
        operationId: mutation.operationId,
        query: mutation.query,
        body: mutation.body,
        accessToken: accessToken,
        failurePhase: NetworkSyncPhase.syncing,
        temporaryIdPrefix: 'offline-relay-',
      );
      _scheduleFlush();
      return queued;
    }
    try {
      final response = await _requestOnline(
        mutation.method,
        mutation.path,
        query: mutation.query,
        body: mutation.body,
        accessToken: accessToken,
        operationId: mutation.operationId,
      );
      await _publishStatus(NetworkSyncPhase.online);
      return response;
    } on _NetworkUnavailable catch (error) {
      final queued = await _queueMutation(
        method: mutation.method,
        path: mutation.path,
        operationId: mutation.operationId,
        query: mutation.query,
        body: mutation.body,
        accessToken: accessToken,
        failurePhase: error.isOffline
            ? NetworkSyncPhase.offline
            : NetworkSyncPhase.degraded,
        temporaryIdPrefix: 'offline-relay-',
      );
      _scheduleRetry(serverDelay: error.retryAfter);
      return queued;
    }
  }

  Future<void> _flushPending() async {
    final token = _lastAccessToken;
    final scope = _activeScope;
    if (_disposed || _syncing || token == null || scope == null) return;
    _debounceTimer?.cancel();
    _syncing = true;
    var processed = 0;
    try {
      var summary = await _offlineStore.summary(scope: scope);
      if (summary.blocked > 0) {
        await _publishStatus(
          NetworkSyncPhase.blocked,
          error: 'Há operações que precisam de revisão.',
        );
      } else if (summary.pending > 0 || summary.retrying > 0) {
        await _publishStatus(NetworkSyncPhase.syncing);
      }

      while (processed < _maxOperationsPerCycle) {
        final rawItem = await _offlineStore.claimNext(
          scope: scope,
          leaseOwner: _leaseOwner,
        );
        if (rawItem == null) break;
        final item = await _offlineStore.resolveReferences(
          rawItem,
          scope: scope,
        );
        final queueId = '${item['queue_id']}';
        final method = '${item['method']}';
        final path = '${item['path']}';
        final query = item['query'] is Map
            ? Map<String, dynamic>.from(item['query'] as Map)
            : null;
        final body = item['body'] is Map
            ? Map<String, dynamic>.from(item['body'] as Map)
            : null;
        try {
          late final Map<String, dynamic> response;
          final relay = _mutationRelay;
          if (relay != null && _canQueue(method, path, body)) {
            try {
              response = await _relayMutation(
                relay,
                method: method,
                path: path,
                operationId: '${item['idempotency_key']}',
                query: query,
                body: body,
              );
            } on MutationRelayUnavailable {
              response = await _requestOnline(
                method,
                path,
                query: query,
                body: body,
                accessToken: token,
                operationId: '${item['idempotency_key']}',
              );
            }
          } else {
            response = await _requestOnline(
              method,
              path,
              query: query,
              body: body,
              accessToken: token,
              operationId: '${item['idempotency_key']}',
            );
          }
          final temporaryId = '${item['temporary_id'] ?? ''}';
          final realId = '${response['id'] ?? ''}';
          if (temporaryId.isNotEmpty && realId.isNotEmpty) {
            await _offlineStore.replaceTemporaryId(
              temporaryId,
              realId,
              scope: scope,
            );
          }
          await _offlineStore.remove(queueId);
          _retryAttempt = 0;
          processed += 1;
        } on _NetworkUnavailable catch (error) {
          final attempt = ((item['attempt_count'] as int?) ?? 0) + 1;
          final delay = error.retryAfter ?? _backoffDelay(attempt);
          final nextAttempt = DateTime.now().toUtc().add(delay);
          await _offlineStore.markRetry(
            queueId,
            attemptCount: attempt,
            nextAttemptAt: nextAttempt,
            error: error.message,
          );
          await _publishStatus(
            error.isOffline
                ? NetworkSyncPhase.offline
                : NetworkSyncPhase.degraded,
            error: error.message,
            nextRetryAt: nextAttempt,
          );
          _scheduleRetry(serverDelay: delay);
          break;
        } on MutationRelayUncertain catch (error) {
          await _offlineStore.markBlocked(queueId, error: error.message);
          await _publishStatus(
            NetworkSyncPhase.blocked,
            error: error.message,
          );
          break;
        } on ApiException catch (error) {
          await _offlineStore.markBlocked(queueId, error: error.message);
          await _publishStatus(
            NetworkSyncPhase.blocked,
            error: error.statusCode == 401
                ? 'Sessão expirada. Entre novamente para revisar a sincronização.'
                : error.message,
          );
          break;
        }
      }

      summary = await _offlineStore.summary(scope: scope);
      if (summary.blocked > 0) {
        await _publishStatus(NetworkSyncPhase.blocked);
      } else if (summary.pending > 0) {
        _scheduleFlush();
      } else if (summary.retrying == 0) {
        await _publishStatus(NetworkSyncPhase.online);
      }
    } finally {
      _syncing = false;
    }
  }

  void _scheduleFlush() {
    if (_disposed || _lastAccessToken == null) return;
    _debounceTimer?.cancel();
    _debounceTimer = Timer(_flushDebounce, () => unawaited(_flushPending()));
  }

  void _scheduleRetry({Duration? serverDelay}) {
    if (_disposed || _lastAccessToken == null) return;
    _retryTimer?.cancel();
    _retryAttempt += 1;
    final delay = serverDelay ?? _backoffDelay(_retryAttempt);
    _retryTimer = Timer(delay, () => unawaited(_flushPending()));
  }

  Duration _backoffDelay(int attempt) {
    final exponent = min(max(attempt - 1, 0), 6);
    final rawMilliseconds =
        _baseRetryDelay.inMilliseconds * pow(2, exponent).toInt();
    final capped = min(rawMilliseconds, _maxRetryDelay.inMilliseconds);
    final jitter = (_operationSequence * 131) % 750;
    return Duration(milliseconds: capped + jitter);
  }

  Future<void> _publishStatus(
    NetworkSyncPhase requestedPhase, {
    String? error,
    DateTime? nextRetryAt,
  }) async {
    final summary = await _offlineStore.summary(scope: _activeScope);
    final phase =
        summary.blocked > 0 && requestedPhase != NetworkSyncPhase.offline
        ? NetworkSyncPhase.blocked
        : requestedPhase == NetworkSyncPhase.online &&
              (summary.pending > 0 || summary.retrying > 0)
        ? NetworkSyncPhase.syncing
        : requestedPhase;
    final next = NetworkSyncStatus(
      phase: phase,
      pending: summary.pending,
      retrying: summary.retrying,
      blocked: summary.blocked,
      lastError: error,
      nextRetryAt: nextRetryAt,
    );
    if (next == _syncStatus || _disposed) return;
    _syncStatus = next;
    _syncStatusController.add(next);
    final online = next.hasConnection;
    if (_lastConnectivityValue != online) {
      _lastConnectivityValue = online;
      _connectivityController.add(online);
    }
  }

  void _rememberSession(String? accessToken) {
    if (accessToken == null) return;
    _lastAccessToken = accessToken;
    _activeScope = _outboxScope(accessToken);
  }

  bool _canCache(String path) {
    if (_requiresOnline(path)) return false;
    return const [
      '/restaurants/',
      '/menu/',
      '/cash-stations/',
      '/tables/',
      '/customers/',
      '/payments/methods/',
      '/printers/',
      '/scales/',
    ].any(path.startsWith);
  }

  bool _canQueue(String method, String path, Map<String, dynamic>? body) {
    if (_requiresOnline(path)) return false;
    if (body?['scale_reading'] != null ||
        body?['weight_kg'] != null ||
        body?['tare_kg'] != null) {
      return false;
    }
    if (path == '/customers/' && method == 'POST') return true;
    if (path.startsWith('/customers/') && method == 'PATCH') return true;
    if (path == '/orders/' && method == 'POST') return true;
    if (path == '/orders/open-table/' && method == 'POST') return true;
    final orderItem = RegExp(r'^/orders/[^/]+/items/$').hasMatch(path);
    if (orderItem && method == 'POST') return true;
    final voidItem = RegExp(
      r'^/orders/[^/]+/items/[^/]+/void/$',
    ).hasMatch(path);
    return voidItem && method == 'DELETE';
  }

  bool _containsPrincipalTemporaryId(
    String path,
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
  ) {
    if (path.contains('offline-relay-')) return true;
    if (query != null && jsonEncode(query).contains('offline-relay-')) {
      return true;
    }
    return body != null && jsonEncode(body).contains('offline-relay-');
  }

  bool _createsResource(String method, String path) {
    if (method != 'POST') return false;
    return path == '/customers/' ||
        path == '/orders/' ||
        path == '/orders/open-table/' ||
        RegExp(r'^/orders/[^/]+/items/$').hasMatch(path);
  }

  bool _requiresOnline(String path) => [
    '/auth/',
    '/cash-auth/',
    '/cash-register/',
    '/print-jobs/',
    '/scales/readings/',
    'latest-reading',
    'checkout-command',
    'claim-agent',
    'release-agent',
    'mark-printed',
    'mark-failed',
    'test-connection',
    '/print/',
    '/pay/',
    '/send-to-kitchen/',
    '/close/',
    '/approve/',
  ].any(path.contains);

  bool _isRetryableStatus(int status) =>
      status == 408 || status == 425 || status == 429 || status >= 500;

  Duration? _retryAfter(String? raw) {
    if (raw == null || raw.trim().isEmpty) return null;
    final seconds = int.tryParse(raw.trim());
    if (seconds != null) return Duration(seconds: max(seconds, 1));
    try {
      final date = HttpDate.parse(raw);
      final difference = date.difference(DateTime.now().toUtc());
      return difference.isNegative ? const Duration(seconds: 1) : difference;
    } on FormatException {
      return null;
    }
  }

  String _nextOperationId() {
    _operationSequence += 1;
    final randomBytes = List<int>.generate(
      18,
      (_) => _secureRandom.nextInt(256),
    );
    return 'pdv-${base64UrlEncode(randomBytes).replaceAll('=', '')}';
  }

  static String _newLeaseOwner() {
    final random = Random.secure();
    final bytes = List<int>.generate(12, (_) => random.nextInt(256));
    return 'engine-${base64UrlEncode(bytes).replaceAll('=', '')}';
  }

  String _cacheKey(String path, Map<String, dynamic>? query, String? token) {
    final sorted = (query?.entries.toList() ?? [])
      ..sort((a, b) => a.key.compareTo(b.key));
    return '${_cacheNamespace(token)}|$path|'
        '${sorted.map((entry) => '${entry.key}=${entry.value}').join('&')}';
  }

  String _cacheNamespace(String? token) =>
      '${Uri.tryParse(baseUrl)?.authority ?? baseUrl}|${_tokenScope(token)}';

  String _outboxScope(String? token) => _cacheNamespace(token);

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
    final error = body['error'];
    if (error is Map) {
      final errorMessage = error['message'];
      if (errorMessage is String && errorMessage.trim().isNotEmpty) {
        return errorMessage.trim();
      }
      final nestedMessages = _validationMessages(errorMessage);
      if (nestedMessages.isNotEmpty) return nestedMessages.join('\n');
    }
    final detail = body['detail'];
    if (detail is String && detail.isNotEmpty) return detail;
    if (detail is List && detail.isNotEmpty) return detail.join(' ');
    final messages = _validationMessages(body);
    if (messages.isNotEmpty) return messages.join('\n');
    if (status == 401) return 'Usuário ou senha inválidos.';
    if (status == 403) {
      return 'Você não tem permissão para realizar esta operação.';
    }
    if (status == 429) {
      return 'O servidor limitou temporariamente as solicitações.';
    }
    if (status >= 500) {
      return 'O servidor encontrou um erro interno (HTTP $status). Tente novamente.';
    }
    return 'Não foi possível concluir a solicitação (HTTP $status).';
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

  Future<void> syncPendingNow() async {
    final scope = _activeScope;
    if (scope != null) await _offlineStore.retryNow(scope: scope);
    _retryTimer?.cancel();
    await _flushPending();
  }

  Future<int> pendingOperations() async =>
      (await _offlineStore.summary(scope: _activeScope)).total;

  Future<void> clearSession() async {
    _retryTimer?.cancel();
    _debounceTimer?.cancel();
    _lastAccessToken = null;
    _activeScope = null;
    _retryAttempt = 0;
    await _publishStatus(NetworkSyncPhase.unknown);
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    _retryTimer?.cancel();
    _debounceTimer?.cancel();
    _client.close();
    await _offlineStore.close();
    await _connectivityController.close();
    await _syncStatusController.close();
  }
}

class _NetworkUnavailable implements Exception {
  const _NetworkUnavailable(
    this.message, {
    this.isOffline = true,
    this.retryAfter,
  });

  final String message;
  final bool isOffline;
  final Duration? retryAfter;
}
