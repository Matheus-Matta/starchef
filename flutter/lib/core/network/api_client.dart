import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;

import 'api_exception.dart';
import 'data_signals.dart';
import 'realtime_client.dart';
import 'mutation_relay.dart';
import 'offline_mutations.dart';
import 'offline_store.dart';

enum NetworkSyncPhase { unknown, online, offline, syncing, degraded, blocked }

/// Renova o access token e devolve o novo valor, ou `null` quando a sessão
/// não pode mais ser recuperada.
typedef AccessTokenRefresher = Future<String?> Function();

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
    required String baseUrl,
    http.Client? client,
    OfflineStore? offlineStore,
    this.requestTimeout = const Duration(seconds: 20),
  }) : _baseUrl = baseUrl,
       _client = client ?? http.Client(),
       _offlineStore = offlineStore ?? OfflineStore();

  static const _flushDebounce = Duration(milliseconds: 450);
  static const _baseRetryDelay = Duration(seconds: 2);
  static const _maxRetryDelay = Duration(minutes: 2);
  static const _maxOperationsPerCycle = 20;

  String _baseUrl;
  String get baseUrl => _baseUrl;
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
  AccessTokenRefresher? _tokenRefresher;
  Future<String?>? _refreshInFlight;

  /// Avisos de dados atualizados, para as telas relerem sem esperar a rede.
  final DataSignals signals = DataSignals();

  Stream<bool> get connectivityChanges => _connectivityController.stream;
  Stream<NetworkSyncStatus> get syncStatusChanges =>
      _syncStatusController.stream;
  NetworkSyncStatus get syncStatus => _syncStatus;
  String? get currentAccessToken => _lastAccessToken;

  /// Troca o servidor ainda na tela de login, sem exigir reiniciar o app.
  /// O escopo autenticado é descartado para impedir que cache/fila de um
  /// servidor seja associado ao próximo login feito em outro endereço.
  Future<void> updateBaseUrl(String value) async {
    final normalized = value.trim().replaceFirst(RegExp(r'/+$'), '');
    if (normalized.isEmpty || normalized == _baseUrl) return;
    _retryTimer?.cancel();
    _debounceTimer?.cancel();
    _baseUrl = normalized;
    _activeScope = null;
    _lastAccessToken = null;
    _lastConnectivityValue = null;
    _retryAttempt = 0;
    await _publishStatus(NetworkSyncPhase.unknown);
  }

  void attachMutationRelay(MutationRelay? relay) {
    _mutationRelay = relay;
  }

  /// Registra quem sabe trocar o refresh token por um novo access token.
  void attachTokenRefresher(AccessTokenRefresher? refresher) {
    _tokenRefresher = refresher;
  }

  /// Namespace da sessão atual (servidor + conta do token).
  ///
  /// Quem guarda dados locais por sessão usa o mesmo valor do cache e da fila,
  /// para que duas contas no mesmo terminal nunca enxerguem os dados uma da
  /// outra. `null` antes do primeiro request autenticado.
  String? get sessionScope => _activeScope;

  /// Endpoint de saúde do servidor, fora do prefixo versionado da API.
  String get healthEndpoint =>
      '${baseUrl.replaceFirst(RegExp(r'/api/v\d+/?$'), '')}/health/';

  /// WS de eventos em tempo real (criação/atualização/remoção de qualquer
  /// modelo da conta). O app nativo autentica pelo token na query — não há
  /// cookie nem Origin de navegador aqui.
  String realtimeSocketUrl(String accessToken) {
    final httpBase = baseUrl.replaceFirst(RegExp(r'/api/v\d+/?$'), '');
    final wsBase = httpBase.replaceFirst(RegExp(r'^http'), 'ws');
    return '$wsBase/ws/realtime/?token=${Uri.encodeComponent(accessToken)}';
  }

  /// Canal dedicado do Caixa Principal. O JWT segue no header Authorization.
  String pdvSocketUrl(String restaurantId) {
    final httpBase = baseUrl.replaceFirst(RegExp(r'/api/v\d+/?$'), '');
    final wsBase = httpBase.replaceFirst(RegExp(r'^http'), 'ws');
    return '$wsBase/ws/pdv/$restaurantId/';
  }

  /// Converte um evento remoto em sinais locais, mantendo a separação por
  /// restaurante como defesa adicional ao filtro feito pelo servidor.
  void applyRealtimeEvent(RealtimeEvent event, {required String restaurantId}) {
    final eventRestaurant = '${event.payload['restaurant_id'] ?? ''}';
    if (eventRestaurant.isNotEmpty && eventRestaurant != restaurantId) return;
    final resource = '${event.payload['resource'] ?? ''}';
    for (final topic in DataSignals.topicsForRealtimeResource(resource)) {
      signals.emit('realtime:$topic');
      signals.emit(topic);
    }
  }

  void notifyRealtimeConnected() {
    for (final topic in DataSignals.realtimeSnapshotTopics) {
      signals.emit('realtime:$topic');
      signals.emit(topic);
    }
  }

  /// Verifica se a API está acessível antes de gastar tentativas da fila.
  ///
  /// Sem esta checagem, cada ciclo com o servidor fora do ar incrementaria o
  /// `attempt_count` das operações e empurraria o backoff para o teto, mesmo
  /// quando o problema é simplesmente falta de rede.
  Future<bool> ping({Duration timeout = const Duration(seconds: 4)}) async {
    try {
      final response = await _client
          .get(Uri.parse(healthEndpoint))
          .timeout(timeout);
      return response.statusCode >= 200 && response.statusCode < 500;
    } catch (_) {
      return false;
    }
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
    final queueableMutation = method != 'GET' && _canQueue(method, path, body);
    final bypassesPrincipal = path.startsWith('/customers/');
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
    // Em modo cliente, ler pelo principal é o caminho normal: é ele que tem a
    // verdade da loja. Com a nuvem fora e a rede local de pé, esta é a única
    // forma de o secundário enxergar um pedido aberto em outro caixa.
    final readRelay = _mutationRelay;
    if (method == 'GET' && readRelay != null) {
      try {
        final decoded = await readRelay.read(
          RelayRead(path: path, query: query),
        );
        await _publishStatus(NetworkSyncPhase.online);
        if (_canCache(path)) {
          await _offlineStore.cache(cacheKey, decoded);
          _signal(path);
        }
        _scheduleFlush();
        return {...decoded, '_from_principal': true};
      } on MutationRelayUnavailable {
        // Principal fora: segue para a nuvem e, se ela também estiver fora,
        // para o cache local.
      } on ApiException {
        // O principal alcançou o servidor e ele recusou; repetir pela nuvem
        // daria o mesmo resultado.
        rethrow;
      }
    }

    // Um caixa secundário nunca grava por conta própria.
    //
    // Se o principal estiver fora, a operação é recusada aqui mesmo: nem pela
    // nuvem, nem na fila local. Escrever direto deixaria o principal com um
    // estado que ele não conhece, e é ele quem os outros caixas leem — o
    // problema só apareceria depois, como pedido divergente ou cobrança
    // repetida. Preferimos recusar agora, com o motivo na tela.
    final preferredRelay = _mutationRelay;
    if (method != 'GET' && preferredRelay != null && !bypassesPrincipal) {
      if (!queueableMutation) {
        throw ApiException(
          'Esta operação precisa do servidor e este caixa é secundário. '
          'Ela é concluída pelo Caixa Principal.',
        );
      }
      try {
        return await _relayMutation(
          preferredRelay,
          method: method,
          path: path,
          operationId: operationId!,
          query: query,
          body: body,
        );
      } on MutationRelayUnavailable catch (error) {
        throw ApiException(
          'O Caixa Principal está indisponível e este caixa é secundário. '
          'Para não gerar divergência, nada é alterado sem ele. '
          '${error.message}',
        );
      } on MutationRelayUncertain catch (error) {
        throw ApiException(error.message);
      }
    }

    try {
      final decoded = await _requestWithSessionRecovery(
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
        _signal(path);
      }
      if (method != 'GET') _signal(path);
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
      // Um secundário já teria sido atendido — ou recusado — pelo principal
      // acima. Chegar aqui com relay significa que a nuvem caiu numa operação
      // que não passa pelo principal, e a fila local continua fora de questão.
      if (method != 'GET' &&
          (_mutationRelay == null || bypassesPrincipal) &&
          _canQueue(method, path, body)) {
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
        isConnectivity: true,
      );
    }
  }

  /// Envia a requisição e, diante de um 401, renova o token uma única vez.
  ///
  /// O retry usa a mesma `Idempotency-Key` da tentativa original: se o servidor
  /// tiver processado a escrita antes de recusar por token vencido, a segunda
  /// chamada é reconhecida como repetição em vez de criar uma venda nova.
  Future<Map<String, dynamic>> _requestWithSessionRecovery(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    String? operationId,
  }) async {
    try {
      return await _requestOnline(
        method,
        path,
        query: query,
        body: body,
        accessToken: accessToken,
        operationId: operationId,
      );
    } on ApiException catch (error) {
      final recoverable =
          error.statusCode == 401 &&
          accessToken != null &&
          _tokenRefresher != null &&
          // O próprio login/refresh devolvendo 401 significa credencial
          // inválida; insistir aqui geraria um laço.
          !path.startsWith('/auth/');
      if (!recoverable) rethrow;

      // Um `null` aqui pode significar credencial recusada ou apenas rede
      // indisponível no instante da renovação. Quem sabe distinguir os dois é
      // quem detém a sessão, então a decisão de encerrá-la fica lá — encerrar
      // por uma queda de rede deslogaria o operador no meio de um turno
      // offline.
      final renewed = await _refreshAccessToken();
      if (renewed == null) rethrow;
      return _requestOnline(
        method,
        path,
        query: query,
        body: body,
        accessToken: renewed,
        operationId: operationId,
      );
    }
  }

  /// Renova o token em uma única chamada compartilhada.
  ///
  /// Várias requisições podem receber 401 ao mesmo tempo; sem este
  /// single-flight cada uma tentaria rotacionar o refresh token e todas menos
  /// a primeira seriam recusadas.
  Future<String?> _refreshAccessToken() {
    final running = _refreshInFlight;
    if (running != null) return running;
    final refresher = _tokenRefresher;
    if (refresher == null) return Future.value(null);

    final attempt = refresher()
        .then((token) {
          if (token != null && token.isNotEmpty) _rememberSession(token);
          return token;
        })
        .catchError((Object _) => null)
        .whenComplete(() => _refreshInFlight = null);
    return _refreshInFlight = attempt;
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
    } on HandshakeException catch (error) {
      // TLS falhou (certificado inválido/expirado, ou https:// apontando pra
      // um servidor que só fala http puro) — sem isso, essa exceção não bate
      // com nenhum catch acima e vaza como "erro inesperado" sem explicação
      // nenhuma pra quem está tentando logar.
      throw _NetworkUnavailable(
        'Falha de TLS ao conectar em $baseUrl: ${error.message}',
      );
    } on http.ClientException catch (error) {
      throw _NetworkUnavailable(
        'Não foi possível acessar a API em $baseUrl: ${error.message}',
      );
    } catch (error) {
      // Rede de segurança: qualquer outra exceção de baixo nível (ex.: erro
      // de certificado embrulhado de outra forma pela plataforma) ainda
      // precisa virar uma mensagem legível em vez de um "erro inesperado"
      // sem contexto na tela de login.
      throw _NetworkUnavailable('Não foi possível falar com $baseUrl: $error');
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
    _signal(path);
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
      final response = await _requestWithSessionRecovery(
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

      // Antes de tocar na fila, confirma que o servidor responde. Sem isso um
      // ciclo com a rede caída consumiria o `attempt_count` de cada operação e
      // levaria o backoff ao teto sem nenhuma chance real de entrega.
      final hasWork = summary.pending > 0 || summary.retrying > 0;
      if (hasWork && !_syncStatus.hasConnection && !await ping()) {
        await _publishStatus(
          NetworkSyncPhase.offline,
          error: 'O servidor não respondeu à verificação de saúde.',
        );
        _scheduleRetry();
        return;
      }

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
          if (relay != null &&
              _canQueue(method, path, body) &&
              !path.startsWith('/customers/')) {
            try {
              response = await _relayMutation(
                relay,
                method: method,
                path: path,
                operationId: '${item['idempotency_key']}',
                query: query,
                body: body,
              );
            } on MutationRelayUnavailable catch (error) {
              // Um secundário não entrega pela nuvem nem para esvaziar a
              // própria fila: o principal precisa registrar a operação, senão
              // ele fica sem saber de uma venda que os outros caixas leem
              // dele. A operação espera o principal voltar.
              throw _NetworkUnavailable(
                'O Caixa Principal está indisponível. ${error.message}',
              );
            }
          } else {
            response = await _requestWithSessionRecovery(
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
          _signal(path);
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
          await _publishStatus(NetworkSyncPhase.blocked, error: error.message);
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

  /// Avisa que o assunto daquela rota mudou localmente.
  void _signal(String path) {
    final topic = DataSignals.topicFor(path);
    if (topic != null) signals.emit(topic);
  }

  void _rememberSession(String? accessToken) {
    if (accessToken == null) return;
    _lastAccessToken = accessToken;
    _activeScope = _outboxScope(accessToken);
  }

  bool _canCache(String path) {
    // A sessão de caixa aberta é lida do cache para que um terminal reiniciado
    // sem rede consiga voltar a vender. Abrir, fechar e movimentar o caixa
    // continuam exigindo servidor, então a cópia local só informa em qual
    // sessão os pedidos entram — ela nunca autoriza uma operação financeira.
    if (path == '/cash-register/current/') return true;
    if (_requiresOnline(path)) return false;
    // Pedidos entram no cache para que o operador consiga abrir, conferir e
    // continuar um pedido já lançado com a rede fora. Sem isso a tela de
    // Pedidos ficava vazia offline e não havia como voltar a um atendimento.
    if (path == '/orders/' || _isOrderScopedRead(path)) return true;
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

  /// Leitura de um pedido específico ou de uma coleção dentro dele.
  static bool _isOrderScopedRead(String path) =>
      RegExp(r'^/orders/[^/]+/(payments/)?$').hasMatch(path);

  bool _canQueue(String method, String path, Map<String, dynamic>? body) {
    if (_requiresOnline(path)) return false;
    // Uma leitura física não pode ser reenviada depois: o peso descreve um
    // instante que já passou.
    if (body?['scale_reading'] != null ||
        body?['weight_kg'] != null ||
        body?['tare_kg'] != null) {
      return false;
    }
    return OfflineMutations.isQueueable(method, path);
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

  bool _createsResource(String method, String path) =>
      OfflineMutations.createsResource(method, path);

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
    '/approve/',
    // Emissão fiscal (NFC-e) exige a SEFAZ/integrador de verdade — enfileirar
    // "silenciosamente" daria uma falsa sensação de nota emitida offline, o
    // que não existe: sem conexão, o operador recebe o erro na hora.
    '/invoices/',
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
        final account =
            '${payload['account_id'] ?? payload['tenant_id'] ?? 'account'}';
        final actor =
            '${payload['user_id'] ?? payload['sub'] ?? 'authenticated'}';
        return '$account:$actor';
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

  /// IDs temporários que já receberam um ID definitivo no servidor.
  Future<Map<String, String>> resolvedTemporaryIds() async {
    final scope = _activeScope;
    if (scope == null) return const {};
    return _offlineStore.resolvedIdMappings(scope: scope);
  }

  /// Acrescenta campos ao corpo de uma mutação que ainda está na fila,
  /// identificada pelo `queue_id` devolvido em `_offline_queue_id` na
  /// resposta otimista. Sem efeito se ela já foi enviada.
  Future<void> patchQueuedBody(
    String queueId,
    Map<String, dynamic> patch,
  ) => _offlineStore.patchBody(queueId, patch);

  Future<int> pendingOperations() async =>
      (await _offlineStore.summary(scope: _activeScope)).total;

  /// Operações da sessão atual, para a tela de revisão da fila.
  Future<List<Map<String, dynamic>>> outboxOperations({
    bool onlyBlocked = false,
  }) async {
    final scope = _activeScope;
    if (scope == null) return const [];
    final items = await _offlineStore.pending(scope: scope, limit: 200);
    if (!onlyBlocked) return items;
    return items.where((item) => item['state'] == 'blocked').toList();
  }

  /// Recoloca uma operação bloqueada na fila após o operador corrigir a causa.
  Future<void> retryBlockedOperation(String queueId) async {
    await _offlineStore.unblock(queueId);
    await _publishStatus(_syncStatus.phase);
    _scheduleFlush();
  }

  /// Descarta uma operação bloqueada. A remoção é definitiva e registrada.
  Future<bool> discardBlockedOperation(String queueId) async {
    final removed = await _offlineStore.discardBlocked(queueId);
    if (removed) await _publishStatus(_syncStatus.phase);
    return removed;
  }

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
    await signals.close();
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
