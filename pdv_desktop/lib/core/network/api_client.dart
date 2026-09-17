import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;

import 'api_exception.dart';
import 'data_signals.dart';
import 'realtime_client.dart';

/// Estado da ligação com o backend.
///
/// Este PDV não opera fora do ar: não existe fila de saída, cache de leitura
/// nem banco local de negócio. As três fases abaixo descrevem apenas o que a
/// tela precisa mostrar no indicador de conexão.
enum NetworkPhase {
  /// Ainda não houve uma requisição para saber.
  unknown,

  /// A última requisição foi respondida.
  online,

  /// A última requisição não chegou ao servidor (rede, DNS, TLS, timeout).
  offline,

  /// O servidor respondeu, mas recusando por sobrecarga (429/5xx).
  degraded,
}

/// Renova o access token e devolve o novo valor, ou `null` quando a sessão
/// não pode mais ser recuperada.
typedef AccessTokenRefresher = Future<String?> Function();

class NetworkStatus {
  const NetworkStatus({required this.phase, this.lastError, this.retryAfter});

  final NetworkPhase phase;
  final String? lastError;
  final Duration? retryAfter;

  bool get hasConnection =>
      phase == NetworkPhase.online || phase == NetworkPhase.degraded;

  @override
  bool operator ==(Object other) =>
      other is NetworkStatus &&
      phase == other.phase &&
      lastError == other.lastError &&
      retryAfter == other.retryAfter;

  @override
  int get hashCode => Object.hash(phase, lastError, retryAfter);
}

/// Cliente HTTP do PDV — o único caminho de dados do aplicativo.
///
/// Toda leitura e toda escrita vão ao backend na hora e o resultado do
/// servidor é a verdade. Se a rede cair, a operação falha na cara do operador,
/// com mensagem: é melhor recusar uma venda do que registrá-la em um lugar que
/// ninguém mais enxerga.
class ApiClient {
  ApiClient({
    required String baseUrl,
    http.Client? client,
    this.requestTimeout = const Duration(seconds: 20),
  }) : _baseUrl = baseUrl,
       _client = client ?? http.Client();

  String _baseUrl;
  String get baseUrl => _baseUrl;
  final http.Client _client;
  final Duration requestTimeout;

  final DataSignals signals = DataSignals();
  final _statusController = StreamController<NetworkStatus>.broadcast();

  String? _lastAccessToken;
  String? _activeScope;
  String? _terminalScope;
  bool _disposed = false;
  int _operationSequence = 0;
  final Random _secureRandom = Random.secure();
  AccessTokenRefresher? _tokenRefresher;
  Future<String?>? _refreshInFlight;
  NetworkStatus _status = const NetworkStatus(phase: NetworkPhase.unknown);

  /// Identidade deste terminal, enviada em toda requisição.
  ///
  /// A sessão de caixa pertence ao par (operador, terminal), e o backend
  /// confere isso para abrir, receber, sangrar, suprir e fechar. Sem estes
  /// dois cabeçalhos o caixa aberto aqui não é reconhecido como sendo daqui.
  String? installationId;
  String? terminalLabel;

  /// Último estado conhecido da ligação, e as mudanças dele.
  NetworkStatus get status => _status;
  Stream<NetworkStatus> get statusChanges => _statusController.stream;

  /// Namespace da sessão atual (conta + usuário do token).
  ///
  /// Use para o que pertence a QUEM está logado.
  String? get sessionScope => _activeScope;

  /// Namespace do TERMINAL (servidor + conta), sem o operador.
  ///
  /// A fila da impressora é do terminal, não de quem está na frente dele: um
  /// cupom que ficou esperando papel no turno da manhã precisa sair quando o
  /// operador da tarde entrar. Incluir o usuário aqui deixaria esse cupom
  /// órfão na troca de turno — ele continuaria no arquivo, invisível para a
  /// fila seguinte, e ninguém saberia que existe.
  ///
  /// A conta continua separando: duas contas no mesmo computador nunca podem
  /// enxergar o papel uma da outra.
  String? get terminalScope => _terminalScope;

  /// O escopo do terminal para um token específico.
  ///
  /// Existe porque quem depende dele — o agente de impressão — precisa saber o
  /// escopo ANTES de fazer qualquer requisição. Derivar do último token usado
  /// deixava o primeiro ciclo do agente sem escopo nenhum: ele caía no caminho
  /// sem fila, imprimia, e o ciclo seguinte (já com escopo) imprimia o mesmo
  /// cupom de novo.
  String terminalScopeFor(String token) =>
      '$baseUrl|${_tokenScope(token).split(':').first}';

  String? get currentAccessToken => _lastAccessToken;

  /// Registra quem sabe trocar o refresh token por um novo access token.
  void attachTokenRefresher(AccessTokenRefresher? refresher) {
    _tokenRefresher = refresher;
  }

  Future<void> updateBaseUrl(String value) async {
    final normalized = value.trim();
    if (normalized.isEmpty || normalized == _baseUrl) return;
    _baseUrl = normalized;
    _lastAccessToken = null;
    _activeScope = null;
    // Outro servidor é outro mundo: a fila da impressora do servidor anterior
    // não pode continuar visível aqui.
    _terminalScope = null;
    _publishStatus(NetworkPhase.unknown);
  }

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

  /// Canal dedicado do terminal. O JWT segue no header Authorization.
  String pdvSocketUrl(String restaurantId) {
    final httpBase = baseUrl.replaceFirst(RegExp(r'/api/v\d+/?$'), '');
    final wsBase = httpBase.replaceFirst(RegExp(r'^http'), 'ws');
    return '$wsBase/ws/pdv/$restaurantId/';
  }

  /// O WebSocket está de pé agora?
  ///
  /// É a prova de que o servidor responde sem gastar uma requisição HTTP para
  /// descobrir isso.
  bool _realtimeConnected = false;
  bool get isRealtimeConnected => _realtimeConnected;

  /// Um evento do servidor mudou algo: as telas interessadas recarregam.
  ///
  /// Sem banco local, o evento não carrega dado nenhum para persistir — ele é
  /// só o aviso de que a leitura de alguém envelheceu.
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
    _realtimeConnected = true;
    _publishStatus(NetworkPhase.online);
    // Reconectar significa que o terminal pode ter perdido eventos enquanto
    // esteve mudo: tudo que a tela mostra é relido.
    for (final topic in DataSignals.realtimeSnapshotTopics) {
      signals.emit('realtime:$topic');
      signals.emit(topic);
    }
  }

  void notifyRealtimeDisconnected() {
    _realtimeConnected = false;
  }

  /// Não há WebSocket cuidando desta conexão (o agente parou, ou nunca subiu).
  void notifyRealtimeUnavailable() {
    _realtimeConnected = false;
  }

  /// O servidor responde agora?
  Future<bool> serverReachable() async {
    if (_realtimeConnected) return true;
    return ping();
  }

  /// Requisição HTTP direta contra `/health/`.
  Future<bool> ping({Duration timeout = const Duration(seconds: 4)}) async {
    try {
      final response = await _client
          .get(Uri.parse(healthEndpoint))
          .timeout(timeout);
      final reachable =
          response.statusCode >= 200 && response.statusCode < 500;
      _publishStatus(reachable ? NetworkPhase.online : NetworkPhase.degraded);
      return reachable;
    } catch (_) {
      _publishStatus(NetworkPhase.offline);
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
    // Toda escrita leva chave de idempotência. A requisição pode ter chegado
    // ao servidor e a resposta ter se perdido no caminho; quando o operador
    // repete o gesto, o backend reconhece a mesma chave e não duplica a venda.
    final operationId = method == 'GET' ? null : _nextOperationId();
    final result = await _requestWithSessionRecovery(
      method,
      path,
      query: query,
      body: body,
      accessToken: accessToken,
      operationId: operationId,
    );
    if (method != 'GET') _signal(path);
    return result;
  }

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
          // O próprio login/refresh devolvendo 401 significa credencial
          // inválida; insistir aqui geraria um laço.
          !path.startsWith('/auth/');
      if (!recoverable) rethrow;
      if (_tokenRefresher == null) rethrow;
      final renewed = await _refreshAccessToken();
      if (renewed == null) rethrow;
      return _requestOnline(
        method,
        path,
        query: query,
        body: body,
        accessToken: renewed,
        // A MESMA chave da primeira tentativa. Se a requisição recusada por
        // token vencido tiver mesmo assim sido aplicada, repetir com chave
        // nova criaria a segunda venda que a idempotência existe para evitar.
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

  /// Valor de cabeçalho HTTP a partir de um texto qualquer.
  ///
  /// Cabeçalho não é UTF-8: `dart:io` recusa qualquer byte acima de 127 com
  /// `FormatException`. Bastava a loja batizar o terminal de "Balcão 01" para
  /// o aplicativo parar de falar com a API. Percent-encoding em vez de tirar
  /// os acentos: o servidor desfaz (`unquote`) e o nome chega inteiro no
  /// cadastro do terminal.
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
      final installation = installationId ?? '';
      if (installation.isNotEmpty) {
        headers['X-Terminal-Id'] = installation;
        final label = terminalLabel ?? '';
        if (label.isNotEmpty) {
          headers['X-Terminal-Name'] = _headerSafe(label);
        }
      }
      final request = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) request.body = jsonEncode(body);
      final streamed = await _client.send(request).timeout(requestTimeout);
      final response = await http.Response.fromStream(streamed);
      // O CÓDIGO DE STATUS VEM PRIMEIRO. Decodificar antes de olhar o status
      // fazia uma resposta de erro sem JSON — a página HTML de um 502 do
      // proxy, ou um 500 do Django — estourar `FormatException` e virar um
      // `ApiException` sem `statusCode`, escondendo a causa real.
      final text = response.bodyBytes.isEmpty
          ? ''
          : utf8.decode(response.bodyBytes, allowMalformed: true);
      final decoded = _decodeBody(text);

      if (response.statusCode < 200 || response.statusCode >= 300) {
        final retryAfter = _retryAfter(response.headers['retry-after']);
        final message = decoded == null
            ? _nonJsonErrorMessage(response.statusCode, text)
            : _messageFor(response.statusCode, decoded);
        if (_isRetryableStatus(response.statusCode)) {
          _publishStatus(
            NetworkPhase.degraded,
            error: message,
            retryAfter: retryAfter,
          );
        } else {
          _publishStatus(NetworkPhase.online);
        }
        throw ApiException(
          message,
          statusCode: response.statusCode,
          retryAfter: retryAfter,
        );
      }
      // Só aqui "resposta inválida" é o diagnóstico certo: o servidor disse
      // que deu certo e mandou algo que não é JSON.
      if (decoded == null) {
        _publishStatus(NetworkPhase.online);
        throw ApiException(
          'A API retornou uma resposta inválida. Servidor configurado: $baseUrl.',
          statusCode: response.statusCode,
        );
      }
      _publishStatus(NetworkPhase.online);
      return decoded;
    } on ApiException {
      rethrow;
    } on FormatException catch (error) {
      // Sobra para o que não é a resposta: URL malformada, corpo que não
      // serializa, cabeçalho fora do ASCII. A mensagem NÃO acusa o endereço do
      // servidor — o problema é inteiramente deste lado.
      throw ApiException(
        'Não foi possível montar a requisição para $path: ${error.message}',
      );
    } on TimeoutException {
      throw _offline(
        'O servidor demorou mais de ${requestTimeout.inSeconds} segundos para responder.',
      );
    } on SocketException catch (error) {
      throw _offline(
        'Não foi possível conectar ao servidor '
        '${error.address?.address ?? Uri.tryParse(baseUrl)?.host ?? baseUrl}.',
      );
    } on HandshakeException catch (error) {
      // TLS falhou (certificado inválido/expirado, ou https:// apontando pra
      // um servidor que só fala http puro) — sem isso, essa exceção não bate
      // com nenhum catch acima e vaza como "erro inesperado" sem explicação.
      throw _offline('Falha de TLS ao conectar em $baseUrl: ${error.message}');
    } on http.ClientException catch (error) {
      throw _offline(
        'Não foi possível acessar a API em $baseUrl: ${error.message}',
      );
    } catch (error) {
      // Rede de segurança: qualquer outra exceção de baixo nível ainda precisa
      // virar uma mensagem legível em vez de um "erro inesperado" sem contexto.
      throw _offline('Não foi possível falar com $baseUrl: $error');
    }
  }

  /// A requisição não chegou ao servidor.
  ///
  /// `isConnectivity` é o que separa, na interface, a recusa que o operador
  /// precisa ler e resolver do estado contínuo de rede fora, que o indicador
  /// de conexão já mostra e não deve virar um alerta novo a cada chamada.
  ApiException _offline(String message) {
    _publishStatus(NetworkPhase.offline, error: message);
    return ApiException(message, isConnectivity: true);
  }

  void _publishStatus(
    NetworkPhase phase, {
    String? error,
    Duration? retryAfter,
  }) {
    if (_disposed) return;
    final next = NetworkStatus(
      phase: phase,
      lastError: error,
      retryAfter: retryAfter,
    );
    if (next == _status) return;
    _status = next;
    _statusController.add(next);
  }

  /// Avisa que o assunto daquela rota mudou.
  void _signal(String path) {
    final topic = DataSignals.topicFor(path);
    if (topic != null) signals.emit(topic);
  }

  void _rememberSession(String? accessToken) {
    if (accessToken == null) return;
    _lastAccessToken = accessToken;
    final scope = _tokenScope(accessToken);
    if (_activeScope == scope) return;
    _activeScope = scope;
    _terminalScope = terminalScopeFor(accessToken);
  }

  Future<void> clearSession() async {
    _lastAccessToken = null;
    _activeScope = null;
    // `_terminalScope` NÃO é limpo: o logout não pode esconder da fila um
    // cupom que ainda está esperando a impressora. Ele só muda quando outra
    // conta entra neste computador.
    _publishStatus(NetworkPhase.unknown);
  }

  String _nextOperationId() {
    _operationSequence += 1;
    final noise = _secureRandom.nextInt(1 << 32).toRadixString(16);
    return '${DateTime.now().microsecondsSinceEpoch.toRadixString(16)}'
        '-$_operationSequence-$noise';
  }

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

  /// Corpo da resposta como mapa, ou `null` quando não é JSON de objeto.
  ///
  /// Uma lista vira `{'results': [...]}`. Um escalar (`"erro"`, `12`) vira
  /// `null` em vez de estourar `TypeError` no cast — outra forma de a mesma
  /// resposta derrubar a chamada por um motivo que não é o real.
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

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    _client.close();
    await _statusController.close();
    await signals.close();
  }
}
