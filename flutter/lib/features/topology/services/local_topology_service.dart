import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/mutation_relay.dart';
import '../../../core/network/relay_origin.dart';
import '../../../core/network/offline_mutations.dart';
import '../../devices/services/local_device_agent.dart';
import '../data/local_topology_store.dart';
import '../domain/lan_addresses.dart';
import '../domain/local_topology_config.dart';
import 'relay_print_fallback.dart';

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
    this.refreshToken = '',
    this.actorName = '',
    this.installationId = '',
    this.terminalName = '',
    LocalTopologyStore? store,
    LocalDeviceAgent? deviceAgent,
  }) : _restaurantId = restaurantId,
       store = store ?? LocalTopologyStore(),
       _printFallback = deviceAgent == null
           ? null
           : RelayPrintFallback(api: api, deviceAgent: deviceAgent);

  static const _timestampTolerance = Duration(minutes: 2);
  static const _healthFreshness = Duration(seconds: 5);
  static const _maximumBodyBytes = 256 * 1024;
  static const _requestBodyTimeout = Duration(seconds: 5);
  static const _maximumQueuedRelays = 64;

  final ApiClient api;
  final String accessToken;

  /// Refresh token DESTE terminal, enviado junto da operação encaminhada.
  ///
  /// A fila do Caixa Principal é durável: uma venda de um secundário pode
  /// esperar horas até a nuvem voltar, e o access token já teria vencido. Sem
  /// o refresh, uma queda longa transformaria a fila inteira em pendência
  /// manual — e o secundário não pode renovar sozinho, porque ele não fala com
  /// o servidor.
  final String refreshToken;
  final String accountId;
  final String actorId;

  /// Nome do operador e da instalação de origem, usados no registro local que
  /// o principal grava antes de a nuvem confirmar.
  final String actorName;
  final String installationId;
  final String terminalName;
  final LocalTopologyStore store;
  final Expando<bool> _respondedRequests = Expando<bool>();
  final RelayPrintFallback? _printFallback;
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

  /// A configuração está válida, mas parada esperando a sessão dizer conta,
  /// operador e unidade.
  ///
  /// O papel do terminal é decidido antes de o PDV carregar os dados — é o que
  /// permite a um Caixa Secundário ler o cardápio pelo principal em vez de
  /// depender da nuvem. Nesse instante a unidade ainda não é conhecida, e sem
  /// esta marca a configuração ficava parada para sempre: nada reaplicava
  /// depois, então o secundário nunca chegava a testar a conexão.
  bool _awaitingIdentity = false;

  /// Último teste de conexão que falhou.
  ///
  /// Enquanto o principal está fora, o monitor já repete o teste a cada
  /// [probeInterval]. Sem esta marca, CADA leitura pagava um teste próprio
  /// antes de cair para a nuvem — a tela inteira travava por segundos a cada
  /// consulta, com o principal desligado.
  DateTime? _lastFailureAt;

  bool get _identityComplete =>
      accountId.trim().isNotEmpty &&
      actorId.trim().isNotEmpty &&
      _restaurantId.trim().isNotEmpty;

  bool get _recentlyUnavailable =>
      _lastFailureAt != null &&
      DateTime.now().difference(_lastFailureAt!) < probeInterval;

  LocalTopologyConfig? get config => _config;
  LocalTopologyStatus get status => _status;

  /// A configuração está gravada e válida, só aguardando a sessão informar a
  /// unidade deste terminal.
  bool get isAwaitingIdentity => _awaitingIdentity;

  void updateRestaurant(String restaurantId) {
    final normalized = restaurantId.trim();
    if (_restaurantId == normalized) return;
    _restaurantId = normalized;
    _lastHealthyAt = null;
    _lastFailureAt = null;
    // A unidade chega depois do papel do terminal, e é ela que faltava para
    // assinar. Sem reaplicar aqui, a configuração continuaria no estado de
    // erro que ela mesma causou — sem servidor aberto no principal e sem
    // nenhum teste de conexão no secundário.
    final pending = _config;
    if (_awaitingIdentity && _identityComplete && pending != null) {
      unawaited(_apply(pending));
    }
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
    // Esperar a sessão dizer a unidade NÃO é uma configuração inválida: é o
    // estado normal de quem acabou de abrir o PDV. Tratar isso como falha
    // desfazia a escolha do operador e, pior, não gravava nada — o caixa
    // reabria amanhã sem saber que era secundário.
    if (_status.phase == LocalTopologyPhase.error && !_awaitingIdentity) {
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

    _awaitingIdentity = false;
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
    if (!_identityComplete) {
      _awaitingIdentity = true;
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
        final addresses = await LanAddresses.discover(next.port);
        // Sem esta linha, "a porta abriu" e "o app nunca chegou aqui" ficam
        // indistinguíveis no diagnóstico — e é a primeira coisa que se
        // pergunta quando um aparelho não conecta.
        AppLogger.instance.info(
          'relay_escutando',
          data: {
            'porta': next.port,
            'enderecos': addresses,
            'node_id': next.nodeId,
          },
        );
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

  @override
  Future<bool> probe() async {
    final current = _config;
    if (_closed || current?.mode != LocalTopologyMode.client) return false;
    try {
      final response = await _signedRequest('GET', '/v1/health');
      final healthy = response['ok'] == true;
      if (!healthy) throw const FormatException('Resposta local inválida.');
      _lastHealthyAt = DateTime.now();
      _lastFailureAt = null;
      _setStatus(
        LocalTopologyStatus(
          phase: LocalTopologyPhase.clientReady,
          message: 'Conectado ao Caixa Principal ${current!.principalHost}.',
        ),
      );
      return true;
    } catch (error) {
      _lastFailureAt = DateTime.now();
      // O motivo entra na mensagem: "indisponível" sozinho não distingue
      // chave errada, relógio fora de hora, restaurante diferente e cabo de
      // rede solto — e era com essa frase que o operador ficava.
      _setStatus(
        LocalTopologyStatus(
          phase: LocalTopologyPhase.unavailable,
          message:
              'Caixa Principal ${current!.principalHost}:${current.port} '
              'indisponível. ${_probeFailureDetail(error)}',
        ),
      );
      AppLogger.instance.warning(
        'relay_cliente_sem_principal',
        data: {
          'host': '${current.principalHost}:${current.port}',
          'causa': '$error',
        },
      );
      return false;
    }
  }

  /// Traduz a falha do teste de conexão para quem está no caixa.
  ///
  /// O principal já responde 401 dizendo o motivo exato (chave, relógio,
  /// conta, restaurante); descartar isso era o que transformava um erro de
  /// configuração de trinta segundos numa manhã perdida.
  static String _probeFailureDetail(Object error) => switch (error) {
    ApiException(:final message) => message,
    MutationRelayUnavailable(:final message) => message,
    FormatException(:final message) => message,
    TimeoutException() => 'Ele não respondeu a tempo pela rede local.',
    SocketException(:final message) =>
      'Não houve resposta na rede local ($message). Confira se o Caixa '
          'Principal está ligado, na mesma rede, e se o firewall do Windows '
          'libera a porta do relay.',
    _ => '$error',
  };

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
      // O secundário não fala com o servidor: quem entrega é o principal. Para
      // que a entrega aconteça em nome de QUEM originou — e não do principal —,
      // as credenciais deste terminal viajam junto, lacradas com a chave de
      // pareamento.
      final credentials = _ownCredentials;
      final envelope = await _signedRequest(
        'POST',
        '/v1/relay',
        body: credentials == null
            ? mutation.toJson()
            : RelayMutation(
                method: mutation.method,
                path: mutation.path,
                operationId: mutation.operationId,
                query: mutation.query,
                body: mutation.body,
                sealedOrigin: LocalRelayAuthenticator.sealOrigin(
                  secret: current!.pairingSecret,
                  origin: credentials,
                ),
              ).toJson(),
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
    if (!recentlyHealthy) {
      // Uma leitura tem para onde cair (cache local e nuvem): repetir o teste
      // que acabou de falhar só atrasaria a tela.
      if (_recentlyUnavailable) {
        throw MutationRelayUnavailable(_status.message);
      }
      if (!await probe()) {
        throw const MutationRelayUnavailable(
          'O Caixa Principal não respondeu ao teste de conexão.',
        );
      }
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

  /// Responde uma leitura pedida por um caixa secundário ou aplicativo.
  ///
  /// O principal serve do **próprio SQLite** (§8, §10): `api.get` é
  /// offline-first, então a resposta sai do banco local na hora e a
  /// reconciliação com a nuvem acontece em paralelo. É por isso que, com a
  /// internet fora e a rede local de pé, o garçom continua enxergando o mesmo
  /// pedido que o caixa.
  Future<Map<String, dynamic>> _serveRead(RelayRead request) async {
    final path = normalizeLocalPath(request.path);
    if (!_validReadPath(path)) {
      throw const ApiException(
        'Leitura não autorizada no relay local.',
        statusCode: 400,
      );
    }
    return api.get(path, query: request.query, accessToken: accessToken);
  }

  /// Traduz o prefixo `/local/...` da API local (§10) para a rota de recurso
  /// que o resto do sistema já conhece.
  ///
  /// `GET /local/orders` e `GET /orders/` são a mesma coisa: um alias mais
  /// legível para quem escreve o cliente de um aparelho novo, sem criar um
  /// segundo conjunto de rotas para manter.
  static String normalizeLocalPath(String path) {
    if (!path.startsWith('/local/')) return path;
    final rest = path.substring('/local/'.length);
    final normalized = rest.startsWith('/') ? rest.substring(1) : rest;
    return normalized.endsWith('/') ? '/$normalized' : '/$normalized/';
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
      // A comanda é a porta de entrada do pedido de salão (a mesa virou só um
      // vínculo dela), então o app do garçom precisa listá-las pelo principal
      // como já faz com mesas e cardápio.
      '/commands/',
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

  /// As credenciais que este terminal envia junto de cada operação.
  ///
  /// `installationId` cai para o `nodeId` da topologia: é o mesmo UUID que já
  /// identifica a instalação no relay, e é ele que vira o `X-Terminal-Id` do
  /// encaminhamento — a sessão de caixa fica registrada na máquina certa.
  RelayOrigin? get _ownCredentials {
    final token = accessToken.trim();
    if (token.isEmpty || actorId.trim().isEmpty) return null;
    return RelayOrigin(
      accessToken: token,
      refreshToken: refreshToken,
      actorId: actorId,
      actorName: actorName,
      installationId: installationId.isNotEmpty
          ? installationId
          : (_config?.nodeId ?? ''),
      terminalName: terminalName,
    );
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
        // A resposta não confere com a chave deste caixa, então o corpo dela
        // não pode ser lido — e é justamente nele que o principal explica a
        // recusa. Com 401, porém, as duas únicas explicações possíveis levam
        // à mesma ação: a chave está diferente da dele. Sem dizer isso, o
        // operador ficava com "resposta não autenticada" e ia procurar
        // problema de rede.
        throw FormatException(
          response.statusCode == HttpStatus.unauthorized
              ? 'O Caixa Principal recusou a chave de pareamento deste '
                    'caixa. Copie a chave em Configurações → Rede local do '
                    'principal e cole aqui.'
              : 'A resposta do Caixa Principal não pôde ser autenticada.',
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
      // Uma linha por requisição recebida: é o que permite responder "o
      // aparelho chegou até aqui?" sem depender do que a tela do celular diz.
      AppLogger.instance.info(
        'relay_requisicao',
        data: {
          'origem': origin?.address ?? 'desconhecida',
          'metodo': request.method,
          'path': request.uri.path,
          'node': request.headers.value('x-starchef-node') ?? '',
        },
      );
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
      final attempt = await _authenticate(request, body);
      final authenticated = attempt.node;
      if (authenticated == null) {
        // O motivo vai no corpo: eram seis causas distintas devolvendo a mesma
        // frase, e quem estava com o celular na mão não tinha como saber se
        // errou a chave, se o relógio estava fora de hora ou se o caixa atende
        // outro restaurante.
        AppLogger.instance.warning(
          'relay_autenticacao_recusada',
          data: {'motivo': attempt.detail, 'path': request.uri.path},
        );
        await _respond(request, HttpStatus.unauthorized, {
          'detail': attempt.detail,
        });
        return;
      }
      AppLogger.instance.info(
        'relay_autenticado',
        data: {
          'node': authenticated.nodeId,
          'ator': authenticated.actorId,
          'path': request.uri.path,
        },
      );
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
      // API local do restaurante (§10). `GET /local/orders` e
      // `POST /local/orders` são a mesma coisa que `/v1/read` e `/v1/relay`,
      // com uma rota mais direta para quem escreve o cliente de um aparelho
      // novo. Os dois caminhos passam pelo mesmo SQLite e pela mesma fila.
      if (path.startsWith('/local/')) {
        final resourcePath = normalizeLocalPath(path);
        if (request.method == 'GET') {
          final result = await _serveRead(
            RelayRead(
              path: resourcePath,
              query: request.uri.queryParameters.isEmpty
                  ? null
                  : Map<String, dynamic>.from(request.uri.queryParameters),
            ),
          );
          await _respond(request, HttpStatus.ok, {
            'ok': true,
            'result': result,
          });
          return;
        }
        final decodedLocal = body.isEmpty ? const {} : jsonDecode(body);
        final payloadLocal = decodedLocal is Map
            ? Map<String, dynamic>.from(decodedLocal)
            : <String, dynamic>{};
        final mutationLocal = RelayMutation(
          method: request.method.toUpperCase(),
          path: resourcePath,
          // A chave de idempotência é do aparelho que pediu: repetir o mesmo
          // POST depois de um timeout não pode criar dois pedidos (§7).
          operationId:
              request.headers.value('x-starchef-operation') ??
              '${payloadLocal['operation_id'] ?? ''}',
          query: request.uri.queryParameters.isEmpty
              ? null
              : Map<String, dynamic>.from(request.uri.queryParameters),
          body: payloadLocal.isEmpty ? null : payloadLocal,
          origin: _openOrigin(
            '${payloadLocal['origin'] ?? ''}',
            authenticated,
          ),
        );
        if (!_validMutationEnvelope(mutationLocal)) {
          throw const FormatException('Envelope da operação local inválido.');
        }
        final result = await _serialRelay(mutationLocal, authenticated);
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
        origin: _openOrigin('${payload['origin'] ?? ''}', authenticated),
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

  /// Abre o lacre da origem e confere que ele descreve quem realmente falou.
  ///
  /// O ator do lacre precisa bater com o ator do cabeçalho assinado: é o
  /// cabeçalho que a chave de pareamento autentica, e quem manda não escolhe
  /// por quem falar. Um lacre ilegível (chave diferente) ou divergente é
  /// simplesmente descartado — a operação segue com as credenciais do
  /// principal, como antes, em vez de ser recusada por um cliente
  /// desatualizado.
  RelayOrigin? _openOrigin(String sealed, _AuthenticatedNode node) {
    final secret = _config?.pairingSecret ?? '';
    if (sealed.isEmpty || secret.isEmpty) return null;
    final origin = LocalRelayAuthenticator.openOrigin(
      secret: secret,
      sealed: sealed,
    );
    if (origin == null) return null;
    if (origin.actorId != node.actorId) {
      AppLogger.instance.warning(
        'relay_origem_divergente',
        data: {'node': node.nodeId, 'ator_assinado': node.actorId},
      );
      return null;
    }
    return origin.installationId.isNotEmpty
        ? origin
        : RelayOrigin(
            accessToken: origin.accessToken,
            refreshToken: origin.refreshToken,
            actorId: origin.actorId,
            actorName: origin.actorName,
            // Sem instalação declarada, o nó do relay já identifica a máquina.
            installationId: node.nodeId,
            terminalName: origin.terminalName,
          );
  }

  /// Diz quem realmente está atendendo, quando a operação abre um pedido.
  ///
  /// Este terminal executa com as credenciais DELE — é ele quem tem a sessão
  /// com a nuvem. Sem essa atribuição o pedido nascia no nome do caixa, e a
  /// comanda saía na cozinha com `ATENDENTE: <caixa>`: o garçom que lançou não
  /// aparecia em lugar nenhum. O ator não vem do corpo, e sim do cabeçalho
  /// assinado com a chave de pareamento — quem manda não escolhe por quem
  /// falar.
  RelayMutation _withActingUser(
    RelayMutation mutation,
    _AuthenticatedNode node,
  ) {
    if (!OfflineMutations.opensOrder(mutation.method, mutation.path)) {
      return mutation;
    }
    return mutation.copyWith(
      body: {...?mutation.body, 'responsible_user': node.actorId},
    );
  }

  Future<Map<String, dynamic>> _serialRelay(
    RelayMutation rawMutation,
    _AuthenticatedNode authenticated,
  ) {
    // O alias `/local/...` é resolvido em um lugar só: daqui para baixo
    // existe apenas a rota de recurso, e o recibo de idempotência fica
    // associado a ela — senão o mesmo pedido enviado pelos dois caminhos
    // pareceria duas operações diferentes.
    final mutation = _withActingUser(
      rawMutation.path.startsWith('/local/')
          ? rawMutation.copyWith(path: normalizeLocalPath(rawMutation.path))
          : rawMutation,
      authenticated,
    );
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
        // Antes da mutação: depois dela os itens já estão marcados como
        // enviados/cancelados, e o responsável pela impressão não teria mais
        // como saber o que mudou nesta chamada.
        final beforeOrder = await _printFallback?.captureBeforeState(mutation);
        // Encaminha em nome de quem originou: o token do secundário, o
        // operador do secundário e a instalação do secundário. As credenciais
        // do principal só entram quando o cliente não mandou as dele (versão
        // antiga do app).
        final response = await api.acceptRelayedMutation(
          mutation,
          accessToken: accessToken,
          origin: mutation.origin,
        );
        await store.saveReceipt(
          accountId: authenticated.accountId,
          nodeId: authenticated.nodeId,
          operationId: mutation.operationId,
          requestHash: requestHash,
          response: response,
        );
        // Quem imprime a comanda/o cupom de cancelamento é este terminal,
        // nunca quem mandou a operação (§ impressão automática por setor):
        // o app do garçom não tem impressora, e um Caixa Secundário que
        // achou a entrega concluída sem o Principal ter alcançado a nuvem
        // também depende disto.
        await _printFallback?.afterAcceptedMutation(
          mutation: mutation,
          beforeOrder: beforeOrder,
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

  /// Autentica a requisição de um nó da rede local.
  ///
  /// A ordem das checagens é deliberada: a chave de pareamento é verificada
  /// ANTES de qualquer coisa sobre conta, restaurante ou relógio. Assim quem
  /// não tem a chave não descobre nada sobre a loja — e quem tem recebe um
  /// motivo específico em vez de um "não autorizado" cego.
  Future<({_AuthenticatedNode? node, String detail})> _authenticate(
    HttpRequest request,
    String body,
  ) async {
    final current = _config;
    if (current?.mode != LocalTopologyMode.principal) {
      return (
        node: null,
        detail: 'Este terminal não está configurado como Caixa Principal.',
      );
    }
    final timestamp = int.tryParse(
      request.headers.value('x-starchef-timestamp') ?? '',
    );
    final nonce = request.headers.value('x-starchef-nonce') ?? '';
    final nodeId = request.headers.value('x-starchef-node') ?? '';
    final account = request.headers.value('x-starchef-account') ?? '';
    final actor = request.headers.value('x-starchef-actor') ?? '';
    final restaurant = request.headers.value('x-starchef-restaurant') ?? '';
    final received = request.headers.value('x-starchef-signature') ?? '';
    if (timestamp == null ||
        nonce.length < 8 ||
        nodeId.isEmpty ||
        actor.isEmpty ||
        account.isEmpty ||
        restaurant.isEmpty) {
      return (
        node: null,
        detail:
            'Requisição incompleta: faltam cabeçalhos de identificação do '
            'aparelho.',
      );
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
      return (
        node: null,
        detail:
            'A chave de pareamento não confere com a deste caixa. Copie a '
            'chave em Configurações → Rede local.',
      );
    }

    // Daqui para baixo o chamador provou que tem a chave: os motivos podem ser
    // específicos sem contar nada da loja para quem não deveria saber.
    final signedAt = DateTime.fromMillisecondsSinceEpoch(
      timestamp * 1000,
      isUtc: true,
    );
    final skew = DateTime.now().toUtc().difference(signedAt);
    if (skew.abs() > _timestampTolerance) {
      final minutes = skew.inMinutes.abs();
      return (
        node: null,
        detail:
            'O relógio do aparelho está ${minutes > 0 ? '$minutes min ' : ''}'
            'fora de hora em relação ao caixa. Ative a data e hora automáticas '
            'nos dois.',
      );
    }
    if (account != accountId) {
      return (
        node: null,
        detail:
            'Este caixa atende outra conta. Entre no aplicativo com um '
            'usuário desta loja.',
      );
    }
    if (restaurant != _restaurantId) {
      return (
        node: null,
        detail:
            'Este caixa está operando outro restaurante. Selecione o mesmo '
            'restaurante nos dois.',
      );
    }

    final now = DateTime.now().toUtc();
    final fresh = await store.consumeNonce(
      accountId: account,
      nodeId: nodeId,
      nonce: nonce,
      seenAt: now,
      expiresBefore: now.subtract(_timestampTolerance),
    );
    if (!fresh) {
      return (
        node: null,
        detail: 'Requisição repetida: esta operação já foi recebida.',
      );
    }
    return (
      node: _AuthenticatedNode(
        accountId: account,
        nodeId: nodeId,
        actorId: actor,
        restaurantId: restaurant,
      ),
      detail: '',
    );
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
    final uri = Uri.tryParse(normalizeLocalPath(mutation.path));
    if (uri == null ||
        uri.hasScheme ||
        uri.hasAuthority ||
        uri.hasQuery ||
        uri.hasFragment ||
        uri.path != normalizeLocalPath(mutation.path) ||
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
    return OfflineMutations.isRelayable(
          mutation.method,
          normalizeLocalPath(mutation.path),
        ) &&
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

  /// Lacra as credenciais de origem com a chave de pareamento.
  ///
  /// A rede local é autenticada (assinatura HMAC + nonce + endereço privado),
  /// mas não é criptografada: um access token em claro dentro do corpo ficaria
  /// legível para quem estivesse no mesmo segmento. Aqui o segredo compartilhado
  /// deriva um keystream (HMAC-SHA256 em contador, no espírito de um HKDF-expand)
  /// que é aplicado ao JSON com XOR. A integridade não depende deste lacre: o
  /// corpo inteiro já vai assinado com a mesma chave, então isto é
  /// encrypt-then-MAC — quem não tem a chave não lê e não consegue trocar.
  static String sealOrigin({required String secret, required RelayOrigin origin}) {
    final nonce = LocalTopologyStore.generateNodeId();
    final plain = utf8.encode(jsonEncode(origin.toJson()));
    final cipher = _xorKeystream(secret: secret, nonce: nonce, data: plain);
    return '$nonce.${base64Url.encode(cipher)}';
  }

  /// Abre o lacre. Devolve `null` para qualquer coisa que não confira —
  /// envelope malformado, chave diferente, campo obrigatório ausente.
  static RelayOrigin? openOrigin({required String secret, required String sealed}) {
    if (sealed.isEmpty) return null;
    final separator = sealed.indexOf('.');
    if (separator <= 0) return null;
    try {
      final nonce = sealed.substring(0, separator);
      final cipher = base64Url.decode(sealed.substring(separator + 1));
      final plain = _xorKeystream(secret: secret, nonce: nonce, data: cipher);
      return RelayOrigin.fromJson(jsonDecode(utf8.decode(plain)));
    } catch (_) {
      return null;
    }
  }

  static List<int> _xorKeystream({
    required String secret,
    required String nonce,
    required List<int> data,
  }) {
    final output = List<int>.filled(data.length, 0);
    final hmac = Hmac(sha256, utf8.encode(secret));
    var offset = 0;
    var counter = 0;
    while (offset < data.length) {
      final block = hmac.convert(utf8.encode('ORIGIN\n$nonce\n$counter')).bytes;
      for (var index = 0; index < block.length && offset < data.length; index++) {
        output[offset] = data[offset] ^ block[index];
        offset += 1;
      }
      counter += 1;
    }
    return output;
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
