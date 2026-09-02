import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;

import '../data/entity_catalog.dart';
import '../logging/app_logger.dart';
import '../data/offline_first_gateway.dart';
import '../data/relay_sync_transport.dart';
import '../data/sync_operation.dart';
import '../data/sync_service.dart';
import 'api_exception.dart';
import 'data_signals.dart';
import 'realtime_client.dart';
import 'mutation_relay.dart';
import 'relay_origin.dart';
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

  /// Armazenamento operacional local. Quando presente, ele — e não a rede —
  /// responde as rotas de entidade (§1). Continua opcional para que a janela
  /// da Balança Rápida e os testes possam usar o cliente sem banco.
  OfflineFirstGateway? _gateway;
  SyncService? _syncService;
  StreamSubscription<SyncSnapshot>? _syncSnapshotSubscription;

  /// Contexto extra da próxima escrita local (mesa, comanda, forma de
  /// pagamento). Passado explicitamente pela tela na chamada.
  OfflineFirstGateway? get localStore => _gateway;
  SyncService? get syncService => _syncService;

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

  /// Define o papel deste terminal na rede local.
  ///
  /// Com um relay anexado, ele é um **Caixa Secundário**: continua gravando no
  /// próprio SQLite e enfileirando, mas quem recebe a fila é o Caixa
  /// Principal, não a nuvem (§8). Antes o secundário não tinha fila nenhuma —
  /// com o principal fora do ar, cada operação era recusada na hora e o
  /// operador ficava sem vender até alguém religar o outro computador.
  void attachMutationRelay(MutationRelay? relay) {
    _mutationRelay = relay;
    _gateway?.relayOnly = relay != null;
    _syncService?.useTransport(syncTransport);
  }

  /// Liga o cliente ao banco operacional e ao serviço de sincronização.
  ///
  /// A partir daqui o PDV é offline-first: leitura vem do SQLite e escrita vai
  /// para o SQLite + fila. O `ApiClient` deixa de ser a fonte de dados e passa
  /// a ser o transporte que o [SyncService] usa para conversar com o backend.
  void attachLocalStore({
    OfflineFirstGateway? gateway,
    SyncService? syncService,
  }) {
    _gateway = gateway;
    gateway?.relayOnly = _mutationRelay != null;
    gateway?.connectivity = () => _syncStatus.hasConnection;
    unawaited(_syncSnapshotSubscription?.cancel());
    _syncSnapshotSubscription = null;
    _syncService = syncService;
    // Quem descobre que a rede caiu passou a ser o `SyncService`, ao tentar
    // entregar a fila. Sem trazer esse resultado de volta para cá, o
    // `syncStatus` ficava congelado em "sincronizando" com a internet fora — e
    // é ele que decide se a comanda de cozinha sai na impressora local ou se o
    // backend vai gerar o `PrintJob`. O sintoma seria o pior possível: a
    // cozinha não recebe comanda nenhuma.
    _syncSnapshotSubscription = syncService?.snapshots.listen(
      (snapshot) => unawaited(_applySyncSnapshot(snapshot)),
    );
  }

  Future<void> _applySyncSnapshot(SyncSnapshot snapshot) async {
    if (_disposed) return;
    await _publishStatus(
      switch (snapshot.phase) {
        SyncPhase.offline => NetworkSyncPhase.offline,
        SyncPhase.degraded => NetworkSyncPhase.degraded,
        SyncPhase.blocked => NetworkSyncPhase.blocked,
        SyncPhase.syncing => NetworkSyncPhase.syncing,
        SyncPhase.idle => NetworkSyncPhase.online,
      },
      error: snapshot.lastError,
      nextRetryAt: snapshot.nextRetryAt,
    );
  }

  /// Espera, por no máximo [timeout], a operação sair da fila local.
  ///
  /// `true` significa que ela chegou ao servidor; `false`, que continua
  /// pendente (ou foi recusada). É o que permite decidir quem imprime uma
  /// comanda de cozinha sem depender de um palpite sobre a conexão: se a
  /// operação subiu, o backend cria o `PrintJob` e o agente imprime; se não,
  /// quem imprime é este terminal.
  Future<bool> awaitDelivery(
    String operationId, {
    Duration timeout = const Duration(seconds: 3),
    Duration pollInterval = const Duration(milliseconds: 150),
  }) async {
    final gateway = _gateway;
    final scope = gateway?.scope;
    if (gateway == null || scope == null || operationId.isEmpty) return false;
    _syncService?.schedulePush(delay: Duration.zero);
    final deadline = DateTime.now().add(timeout);
    while (!_disposed) {
      final pending = await gateway.queue.isPending(
        scope: scope,
        operationId: operationId,
      );
      if (!pending) return true;
      if (!DateTime.now().isBefore(deadline)) return false;
      await Future<void>.delayed(pollInterval);
    }
    return false;
  }

  /// Para onde a fila deste terminal entrega.
  ///
  /// No Caixa Principal (e num terminal sozinho), o backend. Num Caixa
  /// Secundário, o Caixa Principal pela rede local — ele nunca fala com a
  /// nuvem.
  SyncTransport get syncTransport {
    final relay = _mutationRelay;
    return relay == null
        ? _ApiSyncTransport(this)
        : RelaySyncTransport(relay);
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

  /// Aplica um evento do WebSocket ao **banco local**, e só depois avisa as
  /// telas (§11).
  ///
  /// Antes, o evento só emitia um sinal e cada tela reconsultava a API por
  /// conta própria — com a internet fora, o aviso não virava dado nenhum e a
  /// alteração feita na retaguarda simplesmente não existia no caixa. Agora o
  /// registro é lido e persistido; a interface reage à mudança do SQLite.
  ///
  /// A gravação é marcada como REMOTE, portanto **não** gera operação de
  /// saída: é o que corta o laço backend -> WS -> SQLite -> fila -> backend
  /// descrito em §12.
  void applyRealtimeEvent(RealtimeEvent event, {required String restaurantId}) {
    final eventRestaurant = '${event.payload['restaurant_id'] ?? ''}';
    if (eventRestaurant.isNotEmpty && eventRestaurant != restaurantId) return;
    final resource = '${event.payload['resource'] ?? ''}';
    unawaited(_persistRealtimeEvent(event, resource));
    for (final topic in DataSignals.topicsForRealtimeResource(resource)) {
      signals.emit('realtime:$topic');
      signals.emit(topic);
    }
  }

  Future<void> _persistRealtimeEvent(
    RealtimeEvent event,
    String resource,
  ) async {
    final sync = _syncService;
    final entityType = EntityCatalog.typeForRealtimeResource(resource);
    if (sync == null || entityType == null) return;
    final entityId = '${event.payload['id'] ?? ''}';
    // Evento de coleção (`bulk_create`/`update` não passam por signals e vêm
    // sem id): a reconciliação por tipo cobre o caso.
    if (entityId.isEmpty) {
      final descriptor = EntityCatalog.byType(entityType);
      if (descriptor != null) unawaited(sync.pull(descriptor));
      return;
    }
    final applied = await sync.pullEntity(
      entityType: entityType,
      entityId: entityId,
      deleted: '${event.payload['action'] ?? ''}' == 'deleted',
    );
    if (applied) {
      for (final topic in DataSignals.topicsForRealtimeResource(resource)) {
        signals.emit(topic);
      }
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

  /// `localContext` carrega o que só a tela sabe e o corpo da requisição não
  /// diz: a mesa/comanda de um pedido novo, a forma de pagamento escolhida, o
  /// caixa selecionado. É usado apenas para montar o registro local completo —
  /// nada disso é enviado ao servidor.
  Future<Map<String, dynamic>> post(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
    Map<String, dynamic>? localContext,
  }) => _request(
    'POST',
    path,
    body: body,
    accessToken: accessToken,
    localContext: localContext,
  );

  Future<Map<String, dynamic>> patch(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
    Map<String, dynamic>? localContext,
  }) => _request(
    'PATCH',
    path,
    body: body,
    accessToken: accessToken,
    localContext: localContext,
  );

  Future<Map<String, dynamic>> delete(
    String path, {
    Map<String, dynamic>? body,
    String? accessToken,
    Map<String, dynamic>? localContext,
  }) => _request(
    'DELETE',
    path,
    body: body,
    accessToken: accessToken,
    localContext: localContext,
  );

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    Map<String, dynamic>? localContext,
  }) async {
    _rememberSession(accessToken);

    // ------------------------------------------------------------------
    // Caminho offline-first (§3, §4). Vale para os dois papéis: o que muda é
    // para onde a fila entrega. O principal entrega ao backend; o secundário
    // entrega ao principal — e, em ambos, a tela é atendida pelo SQLite deste
    // terminal, sem esperar rede.
    // ------------------------------------------------------------------
    final gateway = _gateway;
    if (gateway != null && gateway.scope != null) {
      if (method == 'GET' && gateway.handlesRead(path)) {
        final local = await _readLocalFirst(gateway, path, query: query);
        if (local != null) return local;
      } else if (method != 'GET' &&
          gateway.handlesWrite(method, path, body)) {
        final result = await gateway.write(
          method,
          path,
          body: body,
          query: query,
          context: localContext,
        );
        _signal(path);
        await _publishStatus(
          _syncStatus.hasConnection
              ? NetworkSyncPhase.syncing
              : _syncStatus.phase,
        );
        _syncService?.schedulePush();
        return {
          ...result.payload,
          '_local_first': true,
          // Diferente de `_offline_pending` (que só diz "ainda não subiu"),
          // isto significa "não havia conexão no momento da gravação". É o
          // que a impressão de cozinha usa para decidir imprimir aqui em vez
          // de esperar o `PrintJob` do backend — marcar sempre faria sair
          // duas comandas para a mesma rodada.
          if (!_syncStatus.hasConnection) '_queued_offline': true,
        };
      }
    }
    final cacheKey = _cacheKey(path, query, accessToken);
    final operationId = method == 'GET' ? null : _nextOperationId();
    final queueableMutation = method != 'GET' && _canQueue(method, path, body);
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
    if (method != 'GET' && preferredRelay != null) {
      // O critério é "o principal sabe executar isto?", e não "isto cabe numa
      // fila". São perguntas diferentes: transferir uma sessão de caixa não
      // pode esperar em fila nenhuma, mas o principal a executa na hora em
      // nome de quem pediu — e é justamente por existirem operações assim que
      // o secundário nunca precisa falar com o servidor.
      if (!OfflineMutations.canBeHandledByPrincipal(method, path)) {
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
      // Um secundário já foi atendido — ou recusado — pelo principal acima.
      // Chegar aqui com relay ligado significaria uma operação que escapou
      // dele, e a fila deste terminal continua fora de questão: ela entregaria
      // à nuvem, que é exatamente o caminho que um secundário não tem.
      if (method != 'GET' &&
          _mutationRelay == null &&
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

  /// Leitura servida pelo SQLite, com sincronização em paralelo (§3).
  ///
  /// A única exceção é a "partida a frio": quando o recurso nunca foi
  /// sincronizado neste terminal, esperar UMA leitura de rede é melhor do que
  /// mostrar a tela vazia na primeira abertura. Depois disso a resposta é
  /// sempre imediata.
  Future<Map<String, dynamic>?> _readLocalFirst(
    OfflineFirstGateway gateway,
    String path, {
    Map<String, dynamic>? query,
  }) async {
    final local = await gateway.read(path, query: query);
    final missing = local['_empty'] == true;
    final emptyPage =
        local['results'] is List && (local['results'] as List).isEmpty;
    final entityType = EntityCatalog.resolve(path)?.type;
    final neverSynced =
        entityType == null || await gateway.lastSyncAt(entityType) == null;

    if (!(missing || (emptyPage && neverSynced))) {
      unawaited(_refreshFromServer(gateway, path, query: query));
      _syncService?.schedulePush();
      return {...local, '_local_first': true};
    }

    try {
      // Pelo mesmo transporte da fila: no Caixa Principal, o backend; num
      // secundário, o Caixa Principal. Buscar direto na nuvem aqui faria um
      // secundário falar com o servidor pelas costas do principal (§8).
      final remote = await syncTransport.send('GET', path, query: query);
      _retryAttempt = 0;
      await _publishStatus(NetworkSyncPhase.online);
      await _storeRemote(gateway, path, remote);
      _signal(path);
      return remote;
    } on TransientSyncFailure catch (error) {
      await _publishStatus(
        error.offline ? NetworkSyncPhase.offline : NetworkSyncPhase.degraded,
        error: error.message,
      );
      _scheduleRetry(serverDelay: error.retryAfter);
      if (missing) {
        // Um detalhe que não existe local nem remotamente precisa continuar
        // sendo um erro para quem chamou — devolver um mapa vazio faria a
        // tela desenhar um pedido fantasma.
        throw ApiException(
          '${local['detail'] ?? 'Registro indisponível offline.'} '
          '${error.message}',
          statusCode: 404,
          isConnectivity: true,
        );
      }
      return {...local, '_local_first': true};
    }
  }

  /// Atualiza o SQLite com a versão do servidor, sem ninguém esperando.
  ///
  /// Ninguém aguarda este future, então nenhuma falha aqui pode escapar: a
  /// tela já foi atendida pela cópia local. O caso comum de erro é o próprio
  /// aplicativo sendo encerrado no meio da reconciliação.
  Future<void> _refreshFromServer(
    OfflineFirstGateway gateway,
    String path, {
    Map<String, dynamic>? query,
  }) async {
    if (_disposed) return;
    try {
      final remote = await syncTransport.send('GET', path, query: query);
      if (_disposed) return;
      _retryAttempt = 0;
      await _publishStatus(NetworkSyncPhase.online);
      await _storeRemote(gateway, path, remote);
      _signal(path);
    } on TransientSyncFailure catch (error) {
      if (_disposed) return;
      await _publishStatus(
        error.offline ? NetworkSyncPhase.offline : NetworkSyncPhase.degraded,
        error: error.message,
      );
      _scheduleRetry(serverDelay: error.retryAfter);
    } on ApiException {
      // O servidor respondeu e recusou (403/404). A cópia local já foi
      // entregue à tela; insistir aqui não muda nada.
    } catch (error) {
      AppLogger.instance.warning(
        'reconciliacao_em_paralelo_falhou',
        data: {'path': path, 'causa': '$error'},
      );
    }
  }

  Future<void> _storeRemote(
    OfflineFirstGateway gateway,
    String path,
    Map<String, dynamic> response,
  ) async {
    if (response['results'] is List) {
      await gateway.applyRemoteCollection(path, response);
      return;
    }
    await gateway.applyRemoteDetail(path, response);
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
    RelayOrigin? origin,
    void Function(RelayOrigin renewed)? onOriginRenewed,
  }) async {
    // Uma operação encaminhada viaja com as credenciais de quem a originou:
    // o token do secundário, não o do principal.
    final effectiveToken = origin != null ? origin.accessToken : accessToken;
    try {
      return await _requestOnline(
        method,
        path,
        query: query,
        body: body,
        accessToken: effectiveToken,
        operationId: operationId,
        origin: origin,
      );
    } on ApiException catch (error) {
      final recoverable =
          error.statusCode == 401 &&
          effectiveToken != null &&
          // O próprio login/refresh devolvendo 401 significa credencial
          // inválida; insistir aqui geraria um laço.
          !path.startsWith('/auth/');
      if (!recoverable) rethrow;

      if (origin != null) {
        // A fila é durável: o access token do secundário vence enquanto a
        // operação espera a nuvem voltar. Ele não pode renovar sozinho (não
        // fala com o servidor), então quem renova é o principal, com o refresh
        // que veio no envelope.
        final renewedOrigin = await _refreshOriginToken(origin);
        if (renewedOrigin == null) rethrow;
        onOriginRenewed?.call(renewedOrigin);
        return _requestOnline(
          method,
          path,
          query: query,
          body: body,
          accessToken: renewedOrigin.accessToken,
          operationId: operationId,
          origin: renewedOrigin,
        );
      }

      if (_tokenRefresher == null) rethrow;
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

  /// Renova o token de um terminal de origem usando o refresh dele.
  ///
  /// Nunca toca na sessão deste terminal: são credenciais de outra pessoa,
  /// que só existem aqui para a entrega acontecer no nome certo.
  Future<RelayOrigin?> _refreshOriginToken(RelayOrigin origin) async {
    if (origin.refreshToken.trim().isEmpty) return null;
    try {
      final response = await _requestOnline(
        'POST',
        '/auth/refresh/',
        body: {'refresh': origin.refreshToken},
      );
      final token = '${response['access'] ?? ''}';
      if (token.isEmpty) return null;
      // A rotação do backend invalida o refresh usado: guardar o novo é o que
      // permite renovar de novo na próxima espera longa.
      return origin.withTokens(
        access: token,
        refresh: '${response['refresh'] ?? ''}',
      );
    } catch (_) {
      return null;
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

  /// Valor de cabeçalho HTTP a partir de um texto qualquer.
  ///
  /// Cabeçalho não é UTF-8: `dart:io` recusa qualquer byte acima de 127 com
  /// `FormatException`, e esse estouro caía no `catch` de baixo virando "a
  /// requisição não pôde ser montada" — uma mensagem que acusava o IP do
  /// servidor por um problema que era nosso. Bastava o terminal se chamar
  /// "Caixa Secundário" ou a loja batizá-lo de "Balcão 01" para o aplicativo
  /// parar de falar com a API até ser reiniciado (reiniciar limpava o nome da
  /// memória, e por isso só o LOGIN DEPOIS DO LOGOUT parecia quebrado: antes
  /// do primeiro login ninguém tinha preenchido o nome ainda).
  ///
  /// Percent-encoding em vez de tirar os acentos: o servidor desfaz
  /// (`unquote`) e o nome chega inteiro no cadastro do terminal. Texto já
  /// ASCII atravessa igual — `unquote` de um nome sem `%` devolve o próprio
  /// nome, então um cliente antigo continua entendido.
  static String _headerSafe(String value) {
    final needsEncoding = value.codeUnits.any((unit) => unit > 127);
    return needsEncoding ? Uri.encodeComponent(value) : value;
  }

  Future<Map<String, dynamic>> _requestOnline(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    String? operationId,
    RelayOrigin? origin,
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
      // De ONDE a operação partiu. A sessão de caixa pertence ao par
      // (operador, terminal), e a checagem vale para receber, sangrar, suprir
      // e fechar — não só para abrir. Mandar no cabeçalho, e não no corpo de
      // cada rota, é o que faz a identidade acompanhar inclusive o replay da
      // fila (que reenvia por aqui).
      //
      // Quando o principal entrega a operação de um secundário, o terminal é o
      // DELE, não o do principal — senão a sessão ficaria registrada na
      // máquina errada.
      final installation = origin?.installationId.isNotEmpty == true
          ? origin!.installationId
          : (_gateway?.installationId ?? '');
      if (installation.isNotEmpty) {
        headers['X-Terminal-Id'] = installation;
        final label = origin?.installationId.isNotEmpty == true
            ? origin!.terminalName
            : (_gateway?.terminalLabel ?? '');
        if (label.isNotEmpty) {
          headers['X-Terminal-Name'] = _headerSafe(label);
        }
      }
      final request = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) request.body = jsonEncode(body);
      final streamed = await _client.send(request).timeout(requestTimeout);
      final response = await http.Response.fromStream(streamed);
      // O CÓDIGO DE STATUS VEM PRIMEIRO. Decodificar antes de olhar o status
      // fazia uma resposta de erro sem JSON — a página HTML de um 502 do proxy,
      // ou um 500 do Django — estourar `FormatException` e virar um
      // `ApiException` sem `statusCode`. A fila trata isso como recusa de
      // negócio e tira a operação de rotação para sempre: uma oscilação de
      // gateway matava permanentemente um fechamento de caixa enfileirado.
      final text = response.bodyBytes.isEmpty
          ? ''
          : utf8.decode(response.bodyBytes, allowMalformed: true);
      final decoded = _decodeBody(text);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        final error = ApiException(
          decoded == null
              ? _nonJsonErrorMessage(response.statusCode, text)
              : _messageFor(response.statusCode, decoded),
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
      // Só aqui "resposta inválida" é o diagnóstico certo: o servidor disse que
      // deu certo e mandou algo que não é JSON.
      if (decoded == null) {
        throw ApiException(
          'A API retornou uma resposta inválida. Servidor configurado: $baseUrl.',
          statusCode: response.statusCode,
        );
      }
      return decoded;
    } on ApiException {
      rethrow;
    } on _NetworkUnavailable {
      rethrow;
    } on FormatException catch (error) {
      // Sobra para o que não é a resposta: URL malformada, corpo que não
      // serializa, cabeçalho fora do ASCII. A resposta em si já foi tratada
      // acima, com o status.
      //
      // A mensagem NÃO acusa mais o endereço do servidor. Ela acusava, e um
      // nome de terminal acentuado — problema inteiramente nosso, deste lado
      // — chegava ao operador como "o IP do backend está errado".
      throw ApiException(
        'Não foi possível montar a requisição para $path: ${error.message}',
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

  /// Executa, no Caixa Principal, uma operação pedida por outro aparelho da
  /// rede local (§8, §9).
  ///
  /// O caminho é o mesmo de uma operação feita no próprio principal: SQLite
  /// primeiro, fila depois. Antes esta função tentava a nuvem na hora e só
  /// enfileirava se a rede falhasse — o resultado era que, com a internet
  /// instável, o garçom esperava o timeout do backend para ver o item entrar
  /// na comanda. Agora a resposta é imediata e o principal continua sendo o
  /// único que fala com a nuvem.
  Future<Map<String, dynamic>> acceptRelayedMutation(
    RelayMutation mutation, {
    required String accessToken,
    RelayOrigin? origin,
  }) =>
      // Tudo o que esta operação gravar — a entidade local e a linha da fila —
      // fica atribuído a quem a originou. A zona é o que mantém essa atribuição
      // colada à cadeia de chamadas: o principal atende as próprias vendas no
      // mesmo isolate, e um campo compartilhado seria lido pela operação errada
      // no primeiro `await` que as intercalasse.
      RelayOrigin.runAs(
        origin,
        () => _acceptRelayedMutation(mutation, accessToken: accessToken),
      );

  Future<Map<String, dynamic>> _acceptRelayedMutation(
    RelayMutation mutation, {
    required String accessToken,
  }) async {
    // A pergunta aqui é "isto pode chegar pela rede local?", não "isto pode
    // esperar numa fila" — são coisas diferentes, e confundi-las travava a
    // balança de um Caixa Secundário: a pesagem é encaminhada ao Principal
    // no instante em que acontece, mas nunca poderia ser enfileirada pelo
    // `ApiClient` como uma venda comum.
    if (!OfflineMutations.isRelayable(mutation.method, mutation.path)) {
      throw ApiException(
        'Operação não autorizada no relay local.',
        statusCode: 400,
      );
    }
    _rememberSession(accessToken);

    final gateway = _gateway;
    if (gateway != null &&
        gateway.scope != null &&
        gateway.handlesWrite(mutation.method, mutation.path, mutation.body)) {
      final result = await gateway.write(
        mutation.method,
        mutation.path,
        body: mutation.body,
        query: mutation.query,
      );
      _signal(mutation.path);
      _syncService?.schedulePush();
      return {
        ...result.payload,
        '_local_first': true,
        if (!_syncStatus.hasConnection) '_queued_offline': true,
      };
    }

    // Rota que o armazenamento local não sabe aplicar (aprovação de
    // supervisor, trabalho de impressão): segue exigindo o servidor, e o
    // aparelho recebe o erro de verdade em vez de uma confirmação falsa.
    final origin = RelayOrigin.current;
    try {
      final response = await _requestWithSessionRecovery(
        mutation.method,
        mutation.path,
        query: mutation.query,
        body: mutation.body,
        accessToken: accessToken,
        operationId: mutation.operationId,
        origin: origin,
      );
      await _publishStatus(NetworkSyncPhase.online);
      return response;
    } on _NetworkUnavailable catch (error) {
      // Esta fila é do principal e não guarda credenciais de terceiros: uma
      // operação de outro caixa que caísse aqui subiria no nome errado. Ela
      // volta como falha temporária, e quem a originou torna a pedir — a
      // operação continua com o dono.
      if (origin != null) {
        throw ApiException(
          'O Caixa Principal não alcançou o servidor agora. ${error.message}',
          // 503 para o secundário reconhecer isto como temporário e tentar de
          // novo, em vez de tratar como recusa de negócio.
          statusCode: 503,
          isConnectivity: true,
        );
      }
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
        // SILENCIOSO. Esta verificação roda a cada ciclo enquanto a rede está
        // fora: anunciar "o servidor não respondeu" a cada tentativa enche a
        // tela de um aviso que não muda nada e que o operador já lê no
        // indicador de conexão. O estado offline é a mensagem.
        await _publishStatus(NetworkSyncPhase.offline);
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
    final legacy = await _offlineStore.summary(scope: _activeScope);
    // O indicador da barra soma as duas filas. Mostrar só a legada faria o
    // PDV parecer "tudo sincronizado" com vendas esperando na fila nova.
    final gateway = _gateway;
    final scope = gateway?.scope;
    final current = gateway == null || scope == null
        ? const SyncQueueSummary()
        : await gateway.queue.summary(scope: scope);
    final summary = OutboxSummary(
      pending: legacy.pending + current.pending + current.processing,
      retrying: legacy.retrying,
      blocked: legacy.blocked + current.failed,
    );
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
    final scope = _outboxScope(accessToken);
    if (_activeScope == scope) return;
    _activeScope = scope;
    // O banco local é vinculado assim que a sessão fica conhecida, e não na
    // abertura do app: antes do login não existe conta, e dados de duas
    // contas não podem compartilhar o mesmo escopo no mesmo terminal.
    _gateway?.bindSession(scope: scope);
    _syncService?.start();
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

  /// Corpo da resposta como mapa, ou `null` quando não é JSON de objeto.
  ///
  /// Uma lista vira `{'results': [...]}` como antes. Um escalar (`"erro"`, `12`)
  /// vira `null` em vez de estourar `TypeError` no cast — outra forma de a
  /// mesma resposta derrubar a chamada por um motivo que não é o real.
  static Map<String, dynamic>? _decodeBody(String text) {
    if (text.isEmpty) return <String, dynamic>{};
    try {
      final raw = jsonDecode(text);
      if (raw is List) return <String, dynamic>{'results': raw};
      if (raw is Map) return Map<String, dynamic>.from(raw);
      return null;
    } on FormatException {
      return null;
    }
  }

  /// Mensagem de um erro que não veio em JSON.
  ///
  /// Guarda o status e um trecho do corpo: sem isso, a causa real (o 502 do
  /// proxy, o 500 do backend) era descartada e o operador via só "resposta
  /// inválida", que não diz para onde olhar.
  static String _nonJsonErrorMessage(int status, String text) {
    final snippet = text
        .replaceAll(RegExp(r'<[^>]*>'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    final detail = snippet.isEmpty
        ? ''
        : ' ${snippet.length > 200 ? '${snippet.substring(0, 200)}…' : snippet}';
    if (status >= 500) {
      return 'O servidor respondeu com erro $status.$detail';
    }
    return 'O servidor respondeu $status sem detalhamento.$detail';
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
    // A fila legada (`offline_outbox`) só existe para entregar o que ficou
    // pendente antes desta versão. A fila operacional é a nova `sync_queue`.
    await _syncService?.syncNow();
  }

  /// Entrega AGORA o que está na fila de vendas, sem esperar o ciclo.
  ///
  /// O recebimento é gravado local-first e sobe pela fila (§4). No gesto de
  /// concluir a venda isso não pode ficar para depois: a emissão fiscal parte
  /// do SERVIDOR, e uma nota que chegasse lá antes dos recebimentos sairia com
  /// o DANFE sem as formas de pagamento — justamente o que o cliente confere.
  ///
  /// Diferente de [syncPendingNow], não puxa dados nem mexe na fila fiscal:
  /// aqui só interessa empurrar o que já está gravado. Sem conexão não faz
  /// nada — a venda segue pela fila, como sempre, e quem imprime é o terminal.
  Future<void> flushSalesQueue() async {
    if (!syncStatus.hasConnection) return;
    await _syncService?.push();
  }

  /// Entrega AGORA a nota fiscal deste pedido e devolve o que o servidor
  /// respondeu.
  ///
  /// A emissão sempre passa pela fila (§16), mesmo com internet — é o que
  /// garante que uma queda no meio do caminho não perca o documento. Mas
  /// esperar o ciclo de 30 segundos para o DANFE sair deixaria o cliente
  /// parado no balcão: com conexão, o gesto de concluir a venda drena a
  /// fila na hora e imprime em seguida.
  ///
  /// `null` quando não há nada enfileirado para o pedido, ou quando o
  /// terminal está sem conexão — aí a nota espera a fila, como sempre.
  Future<Map<String, dynamic>?> flushFiscalForOrder(String orderId) async {
    final gateway = _gateway;
    final scope = _activeScope;
    if (gateway == null || scope == null || !syncStatus.hasConnection) {
      return null;
    }
    await _syncService?.pushFiscal(orderId: orderId);
    final document = await gateway.fiscalQueue.latestForOrder(
      scope: scope,
      orderId: orderId,
    );
    return document?.response;
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
  /// Devolve `true` quando a operação AINDA estava na fila e foi corrigida.
  ///
  /// `false` significa que ela já subiu — quem chama precisa saber disso: é a
  /// diferença entre "eu imprimo esta comanda" e "o backend vai imprimir".
  Future<bool> patchQueuedBody(
    String queueId,
    Map<String, dynamic> patch,
  ) async {
    final gateway = _gateway;
    if (gateway != null &&
        gateway.scope != null &&
        await gateway.queue.patchPayload(queueId, patch)) {
      return true;
    }
    // Fila legada: só continua atendendo o que ficou pendente antes desta
    // versão e as operações retransmitidas por um caixa secundário.
    await _offlineStore.patchBody(queueId, patch);
    return false;
  }

  Future<int> pendingOperations() async {
    final legacy = await _offlineStore.summary(scope: _activeScope);
    final gateway = _gateway;
    final scope = gateway?.scope;
    if (gateway == null || scope == null) return legacy.total;
    return legacy.total + (await gateway.queue.summary(scope: scope)).total;
  }

  /// Operações da sessão atual, para a tela de revisão da fila.
  ///
  /// Junta as duas filas: a operacional (`sync_queue`) e a legada
  /// (`offline_outbox`), que só continua existindo para entregar o que ficou
  /// pendente antes desta versão. A tela de revisão precisa mostrar as duas —
  /// uma venda presa na fila antiga é tão invisível quanto uma presa na nova.
  Future<List<Map<String, dynamic>>> outboxOperations({
    bool onlyBlocked = false,
  }) async {
    final scope = _activeScope;
    if (scope == null) return const [];
    final legacy = await _offlineStore.pending(scope: scope, limit: 200);
    final gateway = _gateway;
    final current = gateway == null || gateway.scope == null
        ? const <Map<String, dynamic>>[]
        : (await gateway.queue.entries(scope: scope)).map(_queueEntryAsOutbox);
    final items = [...current, ...legacy];
    if (!onlyBlocked) return items;
    return items.where((item) => item['state'] == 'blocked').toList();
  }

  /// Traduz uma entrada da fila operacional para o formato que a tela de
  /// revisão já sabe desenhar.
  static Map<String, dynamic> _queueEntryAsOutbox(SyncQueueEntry entry) => {
    'queue_id': entry.operationId,
    'scope': '',
    'method': entry.method,
    'path': entry.path,
    'query': entry.query,
    'body': entry.payload,
    'temporary_id': entry.entityId,
    'idempotency_key': entry.operationId,
    'created_at': entry.createdAt.toIso8601String(),
    'state': switch (entry.status) {
      SyncQueueStatus.failed => 'blocked',
      SyncQueueStatus.pending => entry.attempts > 0 ? 'retry' : 'pending',
      _ => 'pending',
    },
    'attempt_count': entry.attempts,
    'next_attempt_at': entry.nextRetryAt?.toIso8601String(),
    'last_error': entry.lastError,
  };

  /// Recoloca uma operação bloqueada na fila após o operador corrigir a causa.
  Future<void> retryBlockedOperation(String queueId) async {
    final entry = await _findQueueEntry(queueId);
    if (entry != null) {
      await _gateway!.queue.retryFailed(entry.id);
      _syncService?.schedulePush(delay: Duration.zero);
      await _publishStatus(_syncStatus.phase);
      return;
    }
    await _offlineStore.unblock(queueId);
    await _publishStatus(_syncStatus.phase);
    _scheduleFlush();
  }

  /// Descarta uma operação bloqueada. A remoção é definitiva e registrada.
  Future<bool> discardBlockedOperation(String queueId) async {
    final entry = await _findQueueEntry(queueId);
    if (entry != null) {
      final removed = await _gateway!.queue.discardFailed(entry.id);
      if (removed) await _publishStatus(_syncStatus.phase);
      return removed;
    }
    final removed = await _offlineStore.discardBlocked(queueId);
    if (removed) await _publishStatus(_syncStatus.phase);
    return removed;
  }

  Future<SyncQueueEntry?> _findQueueEntry(String operationId) async {
    final gateway = _gateway;
    final scope = gateway?.scope;
    if (gateway == null || scope == null) return null;
    final entries = await gateway.queue.entries(scope: scope);
    for (final entry in entries) {
      if (entry.operationId == operationId) return entry;
    }
    return null;
  }

  Future<void> clearSession() async {
    _retryTimer?.cancel();
    _debounceTimer?.cancel();
    _lastAccessToken = null;
    _activeScope = null;
    _retryAttempt = 0;
    _syncService?.stop();
    _gateway?.clearSession();
    await _publishStatus(NetworkSyncPhase.unknown);
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    _retryTimer?.cancel();
    _debounceTimer?.cancel();
    // Os ciclos de sincronização param junto: um timer sobrevivente tentaria
    // ler um banco já fechado no encerramento do aplicativo.
    await _syncSnapshotSubscription?.cancel();
    await _syncService?.dispose();
    _client.close();
    await _offlineStore.close();
    await _connectivityController.close();
    await _syncStatusController.close();
    await signals.close();
  }
}

/// Adapta o [ApiClient] ao [SyncTransport] esperado pelo [SyncService].
///
/// A diferença para os métodos públicos é que aqui NÃO se passa pelo
/// armazenamento local: este é o caminho que efetivamente fala com o backend.
/// Sem essa separação, drenar a fila reentraria no gateway e a operação seria
/// gravada de novo, gerando o laço descrito em §12.
class _ApiSyncTransport implements SyncTransport {
  const _ApiSyncTransport(this._api);

  final ApiClient _api;

  @override
  Future<bool> ping() => _api.ping();

  @override
  Future<Map<String, dynamic>> send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? idempotencyKey,
    RelayOrigin? origin,
    void Function(RelayOrigin renewed)? onOriginRenewed,
  }) async {
    try {
      return await _api._requestWithSessionRecovery(
        method,
        path,
        query: query,
        body: body,
        accessToken: _api._lastAccessToken,
        operationId: idempotencyKey,
        origin: origin,
        onOriginRenewed: onOriginRenewed,
      );
    } on _NetworkUnavailable catch (error) {
      throw TransientSyncFailure(
        error.message,
        retryAfter: error.retryAfter,
        offline: error.isOffline,
      );
    }
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
