import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/mutation_relay.dart';
import '../../../core/network/offline_mutations.dart';
import '../data/local_topology_store.dart';
import '../domain/local_topology_config.dart';

enum LocalTopologyPhase {
  starting,

  /// Principal operando sozinho: sincroniza com a nuvem, mas ainda não abriu
  /// a porta para outros caixas.
  principalLocalOnly,

  principalReady,
  clientReady,
  unavailable,
  error,
}

class LocalTopologyStatus {
  const LocalTopologyStatus({
    required this.phase,
    required this.message,
    this.addresses = const [],
  });

  final LocalTopologyPhase phase;
  final String message;
  final List<String> addresses;

  bool get ready =>
      phase == LocalTopologyPhase.principalReady ||
      phase == LocalTopologyPhase.clientReady;
}

/// Authenticated LAN relay for the optional principal/client checkout topology.
///
/// It deliberately relays only mutations accepted by [ApiClient]'s outbox
/// allowlist. A client never opens or shares the principal SQLite file.
class LocalTopologyService extends ChangeNotifier implements MutationRelay {
  LocalTopologyService({
    required this.api,
    required this.accessToken,
    required this.accountId,
    required this.actorId,
    required String restaurantId,
    LocalTopologyStore? store,
  }) : _restaurantId = restaurantId,
       store = store ?? LocalTopologyStore();

  static const _timestampTolerance = Duration(minutes: 2);
  static const _healthFreshness = Duration(seconds: 5);
  static const _maximumBodyBytes = 256 * 1024;
  static const _requestBodyTimeout = Duration(seconds: 5);
  static const _maximumQueuedRelays = 64;

  final ApiClient api;
  final String accessToken;
  final String accountId;
  final String actorId;
  final LocalTopologyStore store;
  final Expando<bool> _respondedRequests = Expando<bool>();
  String _restaurantId;

  LocalTopologyConfig? _config;
  LocalTopologyStatus _status = const LocalTopologyStatus(
    phase: LocalTopologyPhase.starting,
    message: 'Preparando rede local...',
  );
  HttpServer? _server;
  Timer? _clientMonitor;
  DateTime? _lastHealthyAt;
  Future<void> _relayTail = Future.value();
  Future<void>? _shutdownFuture;
  int _queuedRelays = 0;
  bool _closed = false;

  LocalTopologyConfig? get config => _config;
  LocalTopologyStatus get status => _status;

  void updateRestaurant(String restaurantId) {
    final normalized = restaurantId.trim();
    if (_restaurantId == normalized) return;
    _restaurantId = normalized;
    _lastHealthyAt = null;
  }

  Future<void> start() async {
    final loaded = await store.load();
    if (_closed) return;
    await _apply(loaded);
  }

  Future<void> reconfigure(LocalTopologyConfig next) async {
    final errors = next.validate();
    if (errors.isNotEmpty) throw ArgumentError(errors.join('\n'));
    if (_closed) return;
    final previous = _config;
    await _apply(next);
    if (_status.phase == LocalTopologyPhase.error) {
      final failure = _status.message;
      if (previous != null) await _apply(previous);
      throw StateError(failure);
    }
    await store.save(next);
  }

  Future<void> _apply(LocalTopologyConfig next) async {
    _setStatus(
      const LocalTopologyStatus(
        phase: LocalTopologyPhase.starting,
        message: 'Aplicando configuração da rede local...',
      ),
    );
    api.attachMutationRelay(null);
    _clientMonitor?.cancel();
    _clientMonitor = null;
    _lastHealthyAt = null;
    final server = _server;
    _server = null;
    if (server != null) await server.close(force: false);
    _config = next;

    final errors = next.validate();
    if (errors.isNotEmpty) {
      // Um secundário mal configurado precisa continuar **bloqueado para
      // escrita**, não virar um caixa solto. Sem o relay anexado o ApiClient
      // trataria este terminal como principal e mandaria vendas direto para a
      // nuvem — exatamente o que a topologia existe para impedir.
      if (next.mode == LocalTopologyMode.client) {
        api.attachMutationRelay(this);
      }
      _setStatus(
        LocalTopologyStatus(
          phase: LocalTopologyPhase.error,
          message: next.principalHost.trim().isEmpty
              ? 'Defina a função deste caixa em Configurações → Rede local: '
                    'ele é o Caixa Principal da loja, ou informe o IP e a '
                    'chave do principal para operar como secundário.'
              : errors.join(' '),
        ),
      );
      return;
    }
    if (accountId.trim().isEmpty ||
        actorId.trim().isEmpty ||
        _restaurantId.trim().isEmpty) {
      if (next.mode == LocalTopologyMode.client) {
        api.attachMutationRelay(this);
      }
      _setStatus(
        const LocalTopologyStatus(
          phase: LocalTopologyPhase.error,
          message:
              'A sessão atual não identifica conta, operador e restaurante '
              'para o pareamento.',
        ),
      );
      return;
    }

    if (next.mode == LocalTopologyMode.principal) {
      // Um caixa sozinho é o principal da própria loja: ele opera e sincroniza
      // com a nuvem sem precisar configurar pareamento. A porta na rede só é
      // aberta quando alguém de fato vai se conectar a ela.
      final sharing = next.lanSharingErrors();
      if (sharing.isNotEmpty) {
        _setStatus(
          LocalTopologyStatus(
            phase: LocalTopologyPhase.principalLocalOnly,
            message:
                'Caixa Principal operando sozinho e sincronizando com a nuvem. '
                'Para conectar outros caixas: ${sharing.join(' ')}',
          ),
        );
        return;
      }
      try {
        final bound = await HttpServer.bind(
          InternetAddress.anyIPv4,
          next.port,
          shared: false,
        );
        if (_closed || _config != next) {
          await bound.close(force: true);
          return;
        }
        _server = bound;
        bound.listen(
          (request) => unawaited(_handleServerRequest(request)),
          onError: (Object error) {
            _setStatus(
              LocalTopologyStatus(
                phase: LocalTopologyPhase.error,
                message: 'Falha no servidor local: $error',
              ),
            );
          },
        );
        final addresses = await _localAddresses(next.port);
        _setStatus(
          LocalTopologyStatus(
            phase: LocalTopologyPhase.principalReady,
            message: 'Caixa Principal aceitando operações autenticadas.',
            addresses: addresses,
          ),
        );
      } on SocketException catch (error) {
        _setStatus(
          LocalTopologyStatus(
            phase: LocalTopologyPhase.error,
            message:
                'Não foi possível abrir a porta ${next.port}: '
                '${error.message}',
          ),
        );
      }
      return;
    }

    api.attachMutationRelay(this);
    await probe();
    _scheduleProbe();
  }

  /// Intervalo até o próximo teste de conexão com o principal.
  ///
  /// Assimétrico de propósito. Com o principal respondendo, nada urgente
  /// depende do teste: uma queda que aconteça entre dois deles é detectada na
  /// hora da gravação, pelo teste sob demanda. Com o principal fora, o
  /// operador está impedido de lançar e esperando — aí vale insistir, porque
  /// cada segundo é caixa parado. O custo é desprezível: um GET assinado de
  /// poucas centenas de bytes na rede local.
  Duration get probeInterval =>
      _status.phase == LocalTopologyPhase.clientReady
      ? const Duration(seconds: 15)
      : const Duration(seconds: 3);

  void _scheduleProbe() {
    _clientMonitor?.cancel();
    if (_closed || _config?.mode != LocalTopologyMode.client) return;
    _clientMonitor = Timer(probeInterval, () async {
      await probe();
      // Reagenda com o intervalo do estado novo: uma queda acelera o ritmo,
      // e a recuperação o desacelera de volta sozinha.
      _scheduleProbe();
    });
  }

  Future<bool> probe() async {
    final current = _config;
    if (_closed || current?.mode != LocalTopologyMode.client) return false;
    try {
      final response = await _signedRequest('GET', '/v1/health');
      final healthy = response['ok'] == true;
      if (!healthy) throw const FormatException('Resposta local inválida.');
      _lastHealthyAt = DateTime.now();
      _setStatus(
        LocalTopologyStatus(
          phase: LocalTopologyPhase.clientReady,
          message: 'Conectado ao Caixa Principal ${current!.principalHost}.',
        ),
      );
      return true;
    } catch (error) {
      _setStatus(
        LocalTopologyStatus(
          phase: LocalTopologyPhase.unavailable,
          message:
              'Caixa Principal ${current!.principalHost}:${current.port} '
              'indisponível.',
        ),
      );
      return false;
    }
  }

  @override
  Future<Map<String, dynamic>> relay(RelayMutation mutation) async {
    final current = _config;
    if (_closed || current?.mode != LocalTopologyMode.client) {
      throw const MutationRelayUnavailable(
        'O relay local não está configurado como cliente.',
      );
    }
    if (!_validMutationEnvelope(mutation)) {
      throw const MutationRelayUnavailable(
        'Esta operação permanece na fila local deste caixa.',
      );
    }
    final recentlyHealthy =
        _lastHealthyAt != null &&
        DateTime.now().difference(_lastHealthyAt!) <= _healthFreshness;
    if (!recentlyHealthy && !await probe()) {
      throw const MutationRelayUnavailable(
        'O Caixa Principal não respondeu ao teste de conexão.',
      );
    }

    try {
      final envelope = await _signedRequest(
        'POST',
        '/v1/relay',
        body: mutation.toJson(),
      );
      final rawResult = envelope['result'];
      if (envelope['ok'] != true || rawResult is! Map) {
        throw const FormatException('Resposta de relay inválida.');
      }
      _lastHealthyAt = DateTime.now();
      return Map<String, dynamic>.from(rawResult);
    } on ApiException {
      rethrow;
    } on MutationRelayUnavailable {
      rethrow;
    } catch (_) {
      final receipt = await _recoverReceipt(mutation);
      if (receipt != null) return receipt;
      throw MutationRelayUncertain(
        'A confirmação do Caixa Principal foi interrompida. A operação não '
        'foi duplicada localmente; consulte o principal antes de repetir.',
      );
    }
  }

  @override
  Future<Map<String, dynamic>> read(RelayRead request) async {
    final current = _config;
    if (_closed || current?.mode != LocalTopologyMode.client) {
      throw const MutationRelayUnavailable(
        'O relay local não está configurado como cliente.',
      );
    }
    final recentlyHealthy =
        _lastHealthyAt != null &&
        DateTime.now().difference(_lastHealthyAt!) <= _healthFreshness;
    if (!recentlyHealthy && !await probe()) {
      throw const MutationRelayUnavailable(
        'O Caixa Principal não respondeu ao teste de conexão.',
      );
    }
    try {
      final envelope = await _signedRequest(
        'POST',
        '/v1/read',
        body: request.toJson(),
      );
      final result = envelope['result'];
      if (envelope['ok'] != true || result is! Map) {
        throw const FormatException('Resposta de leitura inválida.');
      }
      _lastHealthyAt = DateTime.now();
      return Map<String, dynamic>.from(result);
    } on ApiException {
      rethrow;
    } on MutationRelayUnavailable {
      rethrow;
    } catch (error) {
      // Uma leitura pode ser repetida à vontade: não há risco de duplicar
      // nada, então uma falha aqui simplesmente devolve o problema ao
      // chamador, que cai para a cópia local.
      throw MutationRelayUnavailable(
        'Não foi possível ler pelo Caixa Principal: $error',
      );
    }
  }

  /// Responde uma leitura pedida por um caixa secundário.
  ///
  /// O principal serve do próprio `ApiClient`: se ele tiver rede, a resposta
  /// é fresca e o cache dele se atualiza no caminho; se não tiver, sai do
  /// cache dele. Nos dois casos os dois caixas enxergam a mesma coisa, que é
  /// o ponto de existir um principal.
  Future<Map<String, dynamic>> _serveRead(RelayRead request) async {
    if (!_validReadPath(request.path)) {
      throw const ApiException(
        'Leitura não autorizada no relay local.',
        statusCode: 400,
      );
    }
    return api.get(
      request.path,
      query: request.query,
      accessToken: accessToken,
    );
  }

  /// Só rotas de leitura conhecidas, e sem travessia de caminho.
  static bool _validReadPath(String path) {
    final uri = Uri.tryParse(path);
    if (uri == null ||
        uri.hasScheme ||
        uri.hasAuthority ||
        uri.hasQuery ||
        uri.hasFragment ||
        uri.path != path ||
        uri.pathSegments.contains('..') ||
        path.length > 500) {
      return false;
    }
    return const [
      '/orders/',
      '/restaurants/',
      '/menu/',
      '/tables/',
      '/customers/',
      '/payments/methods/',
      '/cash-stations/',
      '/cash-register/',
      '/printers/',
      '/scales/',
    ].any(path.startsWith);
  }

  Future<Map<String, dynamic>?> _recoverReceipt(
    RelayMutation mutation,
  ) async {
    final requestHash = _mutationHash(mutation);
    for (final delay in const [
      Duration(milliseconds: 250),
      Duration(milliseconds: 850),
    ]) {
      await Future<void>.delayed(delay);
      try {
        final envelope = await _signedRequest(
          'GET',
          '/v1/operations/${Uri.encodeComponent(mutation.operationId)}'
          '?hash=${Uri.encodeQueryComponent(requestHash)}',
        );
        final result = envelope['result'];
        if (envelope['ok'] == true && result is Map) {
          return Map<String, dynamic>.from(result);
        }
      } catch (_) {
        // A entrega continua ambígua; uma segunda consulta ainda será tentada.
      }
    }
    return null;
  }

  Future<Map<String, dynamic>> _signedRequest(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final current = _config;
    if (current == null || current.mode != LocalTopologyMode.client) {
      throw const MutationRelayUnavailable('Modo cliente não configurado.');
    }
    if (accountId.trim().isEmpty ||
        actorId.trim().isEmpty ||
        _restaurantId.trim().isEmpty) {
      throw const MutationRelayUnavailable('Conta local não identificada.');
    }
    final restaurant = _restaurantId;
    await _ensurePrivateDestination(current.principalHost);
    final encodedBody = body == null ? '' : jsonEncode(body);
    final timestamp = DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000;
    final nonce = LocalTopologyStore.generateNodeId();
    final signature = LocalRelayAuthenticator.signature(
      secret: current.pairingSecret,
      method: method,
      path: path,
      timestamp: timestamp,
      nonce: nonce,
      account: accountId,
      actor: actorId,
      restaurant: restaurant,
      nodeId: current.nodeId,
      body: encodedBody,
    );
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 2);
    try {
      final uri = Uri.parse('${current.endpoint}$path');
      final request = await client
          .openUrl(method, uri)
          .timeout(const Duration(seconds: 3));
      request.headers
        ..set(HttpHeaders.acceptHeader, 'application/json')
        ..set('x-starchef-timestamp', '$timestamp')
        ..set('x-starchef-nonce', nonce)
        ..set('x-starchef-node', current.nodeId)
        ..set('x-starchef-account', accountId)
        ..set('x-starchef-actor', actorId)
        ..set('x-starchef-restaurant', restaurant)
        ..set('x-starchef-signature', signature);
      if (body != null) {
        request.headers.contentType = ContentType.json;
        request.write(encodedBody);
      }
      final response = await request.close().timeout(
        const Duration(seconds: 6),
      );
      final responseBody = await utf8.decoder.bind(response).join();
      final responseSignature =
          response.headers.value('x-starchef-response-signature') ?? '';
      final expectedResponseSignature =
          LocalRelayAuthenticator.responseSignature(
            secret: current.pairingSecret,
            requestNonce: nonce,
            statusCode: response.statusCode,
            body: responseBody,
          );
      if (!LocalRelayAuthenticator.constantTimeEquals(
        responseSignature,
        expectedResponseSignature,
      )) {
        throw const FormatException(
          'A resposta do Caixa Principal não pôde ser autenticada.',
        );
      }
      final decoded = responseBody.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(responseBody);
      final result = decoded is Map
          ? Map<String, dynamic>.from(decoded)
          : <String, dynamic>{};
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ApiException(
          '${result['detail'] ?? 'O Caixa Principal recusou a operação.'}',
          statusCode: response.statusCode,
        );
      }
      return result;
    } finally {
      client.close(force: true);
    }
  }

  Future<void> _handleServerRequest(HttpRequest request) async {
    try {
      final origin = request.connectionInfo?.remoteAddress;
      if (!isLocalNetworkAddress(origin)) {
        // Uma tentativa de fora da loja é a única coisa aqui que merece
        // atenção humana: sem registro, ela sumiria em silêncio.
        AppLogger.instance.warning(
          'relay_origem_externa_recusada',
          data: {
            'address': origin?.address ?? 'desconhecido',
            'path': request.uri.path,
          },
        );
        await _respond(
          request,
          HttpStatus.forbidden,
          const {'detail': 'O relay aceita somente endereços de rede privada.'},
        );
        return;
      }
      final body = await _readBody(request);
      final authenticated = await _authenticate(request, body);
      if (authenticated == null) {
        await _respond(
          request,
          HttpStatus.unauthorized,
          const {'detail': 'Assinatura local inválida ou expirada.'},
        );
        return;
      }
      final path = request.uri.path;
      if (request.method == 'GET' && path == '/v1/health') {
        await _respond(request, HttpStatus.ok, {
          'ok': true,
          'node_id': _config?.nodeId,
        });
        return;
      }
      if (request.method == 'GET' && path.startsWith('/v1/operations/')) {
        final operationId = Uri.decodeComponent(
          path.substring('/v1/operations/'.length),
        );
        final requestHash = request.uri.queryParameters['hash'] ?? '';
        if (requestHash.isEmpty) {
          throw const FormatException('Hash da operação ausente.');
        }
        final receipt = await store.receipt(
          accountId: authenticated.accountId,
          nodeId: authenticated.nodeId,
          operationId: operationId,
          requestHash: requestHash,
        );
        if (receipt == null) {
          await _respond(
            request,
            HttpStatus.notFound,
            const {'detail': 'Operação ainda não confirmada.'},
          );
          return;
        }
        await _respond(request, HttpStatus.ok, {
          'ok': true,
          'result': receipt,
        });
        return;
      }
      if (request.method == 'POST' && path == '/v1/read') {
        final decoded = jsonDecode(body);
        if (decoded is! Map) {
          throw const FormatException('Payload de leitura inválido.');
        }
        final payload = Map<String, dynamic>.from(decoded);
        final result = await _serveRead(
          RelayRead(
            path: '${payload['path'] ?? ''}',
            query: payload['query'] is Map
                ? Map<String, dynamic>.from(payload['query'] as Map)
                : null,
          ),
        );
        await _respond(request, HttpStatus.ok, {'ok': true, 'result': result});
        return;
      }
      if (request.method != 'POST' || path != '/v1/relay') {
        await _respond(
          request,
          HttpStatus.notFound,
          const {'detail': 'Rota local inexistente.'},
        );
        return;
      }
      final decoded = jsonDecode(body);
      if (decoded is! Map) {
        throw const FormatException('Payload local inválido.');
      }
      final payload = Map<String, dynamic>.from(decoded);
      final mutation = RelayMutation(
        method: '${payload['method'] ?? ''}'.toUpperCase(),
        path: '${payload['path'] ?? ''}',
        operationId: '${payload['operation_id'] ?? ''}',
        query: payload['query'] is Map
            ? Map<String, dynamic>.from(payload['query'] as Map)
            : null,
        body: payload['body'] is Map
            ? Map<String, dynamic>.from(payload['body'] as Map)
            : null,
      );
      if (!_validMutationEnvelope(mutation)) {
        throw const FormatException('Envelope da operação local inválido.');
      }
      final result = await _serialRelay(mutation, authenticated);
      await _respond(request, HttpStatus.ok, {
        'ok': true,
        'result': result,
      });
    } on LocalRelayReceiptConflict catch (error) {
      await _respond(
        request,
        HttpStatus.conflict,
        {'detail': '$error'},
      );
    } on ApiException catch (error) {
      await _respond(
        request,
        error.statusCode ?? HttpStatus.badRequest,
        {'detail': error.message},
      );
    } on FormatException catch (error) {
      await _respond(
        request,
        HttpStatus.badRequest,
        {'detail': error.message},
      );
    } catch (_) {
      await _respond(
        request,
        HttpStatus.internalServerError,
        const {'detail': 'Falha interna no relay do Caixa Principal.'},
      );
    }
  }

  Future<Map<String, dynamic>> _serialRelay(
    RelayMutation mutation,
    _AuthenticatedNode authenticated,
  ) {
    if (_queuedRelays >= _maximumQueuedRelays) {
      throw ApiException(
        'O Caixa Principal está processando muitas operações locais.',
        statusCode: HttpStatus.tooManyRequests,
      );
    }
    _queuedRelays += 1;
    final requestHash = _mutationHash(mutation);
    final completer = Completer<Map<String, dynamic>>();
    _relayTail = _relayTail.then((_) async {
      try {
        final existing = await store.receipt(
          accountId: authenticated.accountId,
          nodeId: authenticated.nodeId,
          operationId: mutation.operationId,
          requestHash: requestHash,
        );
        if (existing != null) {
          completer.complete(existing);
          return;
        }
        final response = await api.acceptRelayedMutation(
          mutation,
          accessToken: accessToken,
        );
        await store.saveReceipt(
          accountId: authenticated.accountId,
          nodeId: authenticated.nodeId,
          operationId: mutation.operationId,
          requestHash: requestHash,
          response: response,
        );
        completer.complete(response);
      } catch (error, stackTrace) {
        completer.completeError(error, stackTrace);
      } finally {
        _queuedRelays -= 1;
      }
    });
    return completer.future;
  }

  Future<_AuthenticatedNode?> _authenticate(
    HttpRequest request,
    String body,
  ) async {
    final current = _config;
    if (current?.mode != LocalTopologyMode.principal) return null;
    final timestamp = int.tryParse(
      request.headers.value('x-starchef-timestamp') ?? '',
    );
    final nonce = request.headers.value('x-starchef-nonce') ?? '';
    final nodeId = request.headers.value('x-starchef-node') ?? '';
    final account = request.headers.value('x-starchef-account') ?? '';
    final actor = request.headers.value('x-starchef-actor') ?? '';
    final restaurant = request.headers.value('x-starchef-restaurant') ?? '';
    final received = request.headers.value('x-starchef-signature') ?? '';
    // Conta e restaurante são checados com igualdade: o principal só atende a
    // própria loja. O ATOR não — quem opera o outro nó não é necessariamente a
    // mesma pessoa logada aqui. Era o que travava o app do garçom: cada garçom
    // entra com o próprio usuário e todas as requisições voltavam 401. O que
    // autoriza o nó é a chave de pareamento; o ator viaja junto para
    // identificar quem pediu, não para dar permissão (a operação é executada
    // com a credencial deste terminal de qualquer forma).
    if (timestamp == null ||
        nonce.length < 8 ||
        nodeId.isEmpty ||
        actor.isEmpty ||
        account != accountId ||
        restaurant != _restaurantId) {
      return null;
    }
    final signedAt = DateTime.fromMillisecondsSinceEpoch(
      timestamp * 1000,
      isUtc: true,
    );
    if (DateTime.now().toUtc().difference(signedAt).abs() >
        _timestampTolerance) {
      return null;
    }
    final expected = LocalRelayAuthenticator.signature(
      secret: current!.pairingSecret,
      method: request.method,
      path: request.uri.toString(),
      timestamp: timestamp,
      nonce: nonce,
      account: account,
      actor: actor,
      restaurant: restaurant,
      nodeId: nodeId,
      body: body,
    );
    if (!LocalRelayAuthenticator.constantTimeEquals(received, expected)) {
      return null;
    }
    final now = DateTime.now().toUtc();
    final fresh = await store.consumeNonce(
      accountId: account,
      nodeId: nodeId,
      nonce: nonce,
      seenAt: now,
      expiresBefore: now.subtract(_timestampTolerance),
    );
    return fresh
        ? _AuthenticatedNode(
            accountId: account,
            nodeId: nodeId,
            actorId: actor,
            restaurantId: restaurant,
          )
        : null;
  }

  Future<String> _readBody(HttpRequest request) async {
    final bytes = <int>[];
    await for (final chunk in request.timeout(_requestBodyTimeout)) {
      bytes.addAll(chunk);
      if (bytes.length > _maximumBodyBytes) {
        throw const FormatException('Payload local excede 256 KB.');
      }
    }
    return utf8.decode(bytes);
  }

  bool _validMutationEnvelope(RelayMutation mutation) {
    final uri = Uri.tryParse(mutation.path);
    if (uri == null ||
        uri.hasScheme ||
        uri.hasAuthority ||
        uri.hasQuery ||
        uri.hasFragment ||
        uri.path != mutation.path ||
        uri.pathSegments.contains('..')) {
      return false;
    }
    // A lista de operações vive em `OfflineMutations`, compartilhada com a
    // fila do `ApiClient`. Enquanto ela era duplicada aqui, as duas
    // divergiram e fechar/pagar passaram a contornar o principal.
    final bodyRestaurant = '${mutation.body?['restaurant'] ?? ''}';
    final queryRestaurant = '${mutation.query?['restaurant'] ?? ''}';
    final restaurantMatches =
        (bodyRestaurant.isEmpty || bodyRestaurant == _restaurantId) &&
        (queryRestaurant.isEmpty || queryRestaurant == _restaurantId);
    return OfflineMutations.isRelayable(mutation.method, mutation.path) &&
        restaurantMatches &&
        mutation.path.length <= 500 &&
        RegExp(r'^[A-Za-z0-9._:-]{8,160}$').hasMatch(mutation.operationId);
  }

  Future<void> _respond(
    HttpRequest request,
    int statusCode,
    Map<String, dynamic> body,
  ) async {
    final response = request.response;
    if (_respondedRequests[request] == true) return;
    _respondedRequests[request] = true;
    final encoded = jsonEncode(body);
    final nonce = request.headers.value('x-starchef-nonce') ?? '';
    final secret = _config?.pairingSecret ?? '';
    response.statusCode = statusCode;
    response.headers.contentType = ContentType.json;
    response.headers.set(
      'x-starchef-response-signature',
      LocalRelayAuthenticator.responseSignature(
        secret: secret,
        requestNonce: nonce,
        statusCode: statusCode,
        body: encoded,
      ),
    );
    response.write(encoded);
    await response.close();
  }

  static String _mutationHash(RelayMutation mutation) {
    final canonical = jsonEncode(_canonicalJson(mutation.toJson()));
    return sha256.convert(utf8.encode(canonical)).toString();
  }

  static Object? _canonicalJson(Object? value) {
    if (value is Map) {
      final entries = value.entries.toList()
        ..sort((left, right) => '${left.key}'.compareTo('${right.key}'));
      return <String, Object?>{
        for (final entry in entries)
          '${entry.key}': _canonicalJson(entry.value),
      };
    }
    if (value is List) return value.map(_canonicalJson).toList();
    return value;
  }

  /// O endereço pertence à rede local desta loja?
  ///
  /// O Caixa Principal só conversa com quem está na mesma rede: qualquer
  /// origem fora das faixas privadas é recusada antes mesmo da verificação de
  /// assinatura.
  ///
  /// Loopback passa em qualquer família, porque é o próprio terminal. Fora
  /// dele, só IPv4 privado: a topologia é IPv4 — o socket nem escuta em IPv6 —
  /// e aceitar uma família que ninguém usa só ampliaria a superfície.
  ///
  /// O socket é aberto em todas as interfaces de propósito. Amarrá-lo a um IP
  /// específico deixaria o principal inalcançável depois de uma troca de IP
  /// pelo DHCP — uma falha silenciosa, com o terminal parecendo no ar — e
  /// quebraria máquinas com mais de uma placa de rede. A proteção real é este
  /// filtro somado à assinatura HMAC, que uma origem externa não teria como
  /// produzir.
  static bool isLocalNetworkAddress(InternetAddress? address) {
    if (address == null) return false;
    if (address.isLoopback) return true;
    final bytes = address.rawAddress;
    if (bytes.length != 4) return false;
    return bytes[0] == 10 ||
        (bytes[0] == 172 && bytes[1] >= 16 && bytes[1] <= 31) ||
        (bytes[0] == 192 && bytes[1] == 168) ||
        (bytes[0] == 169 && bytes[1] == 254);
  }

  Future<void> shutdown() =>
      _shutdownFuture ??= _performShutdown();

  Future<void> _performShutdown() async {
    _closed = true;
    api.attachMutationRelay(null);
    _clientMonitor?.cancel();
    _clientMonitor = null;
    final server = _server;
    _server = null;
    if (server != null) await server.close(force: false);
    await _relayTail;
    await store.close();
  }

  void _setStatus(LocalTopologyStatus next) {
    if (_closed) return;
    _status = next;
    notifyListeners();
  }

  @override
  void dispose() {
    unawaited(shutdown());
    super.dispose();
  }

  static Future<List<String>> _localAddresses(int port) async {
    final values = <String>[];
    try {
      final interfaces = await NetworkInterface.list(
        type: InternetAddressType.IPv4,
        includeLoopback: false,
      );
      for (final interface in interfaces) {
        for (final address in interface.addresses) {
          values.add('${address.address}:$port');
        }
      }
    } catch (_) {}
    return values.toSet().toList()..sort();
  }

  static Future<void> _ensurePrivateDestination(String host) async {
    try {
      final addresses = await InternetAddress.lookup(
        host,
        type: InternetAddressType.IPv4,
      ).timeout(const Duration(seconds: 2));
      if (addresses.isEmpty || addresses.any((item) => !isLocalNetworkAddress(item))) {
        throw const MutationRelayUnavailable(
          'O Caixa Principal precisa estar em uma rede IPv4 privada.',
        );
      }
    } on MutationRelayUnavailable {
      rethrow;
    } on TimeoutException {
      throw const MutationRelayUnavailable(
        'O endereço do Caixa Principal não respondeu ao DNS local.',
      );
    } on SocketException {
      throw const MutationRelayUnavailable(
        'O endereço do Caixa Principal não foi encontrado na rede local.',
      );
    }
  }

}

abstract final class LocalRelayAuthenticator {
  static String signature({
    required String secret,
    required String method,
    required String path,
    required int timestamp,
    required String nonce,
    required String account,
    required String actor,
    required String restaurant,
    required String nodeId,
    required String body,
  }) {
    final canonical = [
      method.toUpperCase(),
      path,
      '$timestamp',
      nonce,
      account,
      actor,
      restaurant,
      nodeId,
      body,
    ].join('\n');
    final digest = Hmac(
      sha256,
      utf8.encode(secret),
    ).convert(utf8.encode(canonical));
    return base64UrlEncode(digest.bytes).replaceAll('=', '');
  }

  static String responseSignature({
    required String secret,
    required String requestNonce,
    required int statusCode,
    required String body,
  }) {
    final canonical = [
      'RESPONSE',
      requestNonce,
      '$statusCode',
      body,
    ].join('\n');
    final digest = Hmac(
      sha256,
      utf8.encode(secret),
    ).convert(utf8.encode(canonical));
    return base64UrlEncode(digest.bytes).replaceAll('=', '');
  }

  static bool constantTimeEquals(String left, String right) {
    final a = utf8.encode(left);
    final b = utf8.encode(right);
    var difference = a.length ^ b.length;
    final length = a.length > b.length ? a.length : b.length;
    for (var index = 0; index < length; index++) {
      final av = index < a.length ? a[index] : 0;
      final bv = index < b.length ? b[index] : 0;
      difference |= av ^ bv;
    }
    return difference == 0;
  }
}

class _AuthenticatedNode {
  const _AuthenticatedNode({
    required this.accountId,
    required this.nodeId,
    required this.actorId,
    required this.restaurantId,
  });

  final String accountId;
  final String nodeId;
  final String actorId;
  final String restaurantId;
}
