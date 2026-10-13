part of 'api_client.dart';

/// A NUVEM como segundo servidor: o envio, e com qual sessão.
///
/// O PDV faz DOIS logins ao entrar (`login_pela_nuvem.dart`) e guarda as duas
/// sessões. Para a loja vai o token da loja; para a nuvem, o da nuvem — cada
/// um assinado pela SECRET_KEY do seu servidor. Antes o desvio mandava o da
/// loja à nuvem, que respondia "credenciais inválidas" em toda tela.
extension ApiClientNuvem on ApiClient {
  /// A requisição repetida contra a nuvem.
  ///
  /// **Leva a MESMA chave de idempotência da tentativa na loja.** É a regra
  /// que impede a duplicação: a loja volta, a fila do terminal reenvia a
  /// operação, e a loja reconhece a chave — porque o registro de idempotência
  /// desceu da nuvem pela sincronização. Uma chave nova a cada tentativa
  /// transformaria cada desvio numa segunda venda.
  ///
  /// Requisição CRUA de propósito: sem recuperação de sessão e sem publicar
  /// estado de rede. O token da loja não vale aqui — ele é assinado com a
  /// `SECRET_KEY` daquela instalação —, então o que passa é o cabeçalho que
  /// veio, e a nuvem aceita ou recusa. Uma tentativa de renovar sessão contra
  /// a nuvem confundiria as duas credenciais.
  ///
  /// Com a SESSÃO DA NUVEM (o segundo login), vai com o token dela: o da loja
  /// é assinado com outra SECRET_KEY e a nuvem nunca o aceita. Expirado, é
  /// renovado NA NUVEM e a requisição repete uma vez.
  Future<Map<String, dynamic>> _naNuvem(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    String? operationId,
  }) async {
    final temSessao = _nuvemAccess.isNotEmpty;
    Future<Map<String, dynamic>> enviar() => _enviarANuvem(
      method,
      path,
      query: query,
      body: body,
      accessToken: temSessao ? _nuvemAccess : accessToken,
      operationId: operationId,
    );
    try {
      return await enviar();
    } on ApiException catch (erro) {
      if (!temSessao || erro.statusCode != 401 || !await _renovarNaNuvem()) {
        rethrow;
      }
      return enviar();
    }
  }

  /// Renova a sessão da nuvem NA NUVEM (o refresh da loja não vale lá).
  Future<bool> _renovarNaNuvem() async {
    if (_nuvemRefresh.isEmpty) return false;
    try {
      final resposta = await _enviarANuvem(
        'POST',
        '/auth/refresh/',
        body: {'refresh': _nuvemRefresh, 'no_cookie': true},
      );
      final access = '${resposta['access'] ?? ''}';
      if (access.isEmpty) return false;
      _nuvemAccess = access;
      _nuvemRefresh = '${resposta['refresh'] ?? _nuvemRefresh}';
      await _aoRenovarANuvem?.call(_nuvemAccess, _nuvemRefresh);
      return true;
    } on ApiException {
      return false;
    }
  }

  Future<Map<String, dynamic>> _enviarANuvem(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    String? operationId,
  }) async {
    final uri = cloudFallback.enderecoPara(path, query);
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (accessToken != null) headers['Authorization'] = 'Bearer $accessToken';
    if (operationId != null) headers['Idempotency-Key'] = operationId;
    _addTerminalHeaders(headers);
    try {
      final pedido = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) pedido.body = jsonEncode(body);
      final transmitida = await _client.send(pedido).timeout(requestTimeout);
      final resposta = await http.Response.fromStream(transmitida);
      ultimoServerTiming = resposta.headers['server-timing'];
      final texto = resposta.bodyBytes.isEmpty
          ? ''
          : utf8.decode(resposta.bodyBytes, allowMalformed: true);
      final decodificado = ApiClient._decodeBody(texto);
      if (resposta.statusCode < 200 || resposta.statusCode >= 300) {
        throw ApiException(
          decodificado == null
              ? ApiClient._nonJsonErrorMessage(resposta.statusCode, texto)
              : _messageFor(resposta.statusCode, decodificado),
          statusCode: resposta.statusCode,
          code: codigoDoErro(decodificado),
          data: dadosDoErro(decodificado),
        );
      }
      return decodificado ?? <String, dynamic>{};
    } on ApiException {
      rethrow;
    } catch (error) {
      // A nuvem não atendeu. Quem chamou volta a mostrar o erro da LOJA, que é
      // onde o operador pode agir.
      throw ApiException(
        'A nuvem também não respondeu: $error',
        isConnectivity: true,
      );
    }
  }
}
