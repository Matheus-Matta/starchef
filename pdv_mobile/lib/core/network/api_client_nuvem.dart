part of 'api_client.dart';

/// A NUVEM como segundo servidor: o envio, e com qual sessão.
///
/// O app faz DOIS logins ao entrar (`login_pela_nuvem.dart`) e guarda as duas
/// sessões. Para a loja vai o token da loja; para a nuvem, o da nuvem — cada
/// um assinado pela SECRET_KEY do seu servidor. Antes o desvio mandava o da
/// loja à nuvem, que respondia "credenciais inválidas" em toda tela.
extension ApiClientNuvem on ApiClient {
  /// A requisição repetida contra a nuvem, com a MESMA chave de idempotência.
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
    String? idempotencyKey,
  }) async {
    final temSessao = _nuvemAccess?.isNotEmpty ?? false;
    Future<Map<String, dynamic>> enviar() => _enviarANuvem(
      method,
      path,
      query: query,
      body: body,
      accessToken: temSessao ? _nuvemAccess : accessToken,
      idempotencyKey: idempotencyKey,
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
    final refresh = _nuvemRefresh;
    if (refresh == null || refresh.isEmpty) return false;
    try {
      final resposta = await _enviarANuvem(
        'POST',
        '/auth/refresh/',
        body: {'refresh': refresh, 'no_cookie': true},
      );
      final access = '${resposta['access'] ?? ''}';
      if (access.isEmpty) return false;
      _nuvemAccess = access;
      _nuvemRefresh = '${resposta['refresh'] ?? refresh}';
      await _onCloudTokensChanged?.call(_nuvemAccess!, _nuvemRefresh!);
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
    String? idempotencyKey,
  }) async {
    final uri = cloudFallback.enderecoPara(path, query);
    final pedido = http.Request(method, uri)
      ..headers['accept'] = 'application/json';
    if (accessToken?.isNotEmpty ?? false) {
      pedido.headers['authorization'] = 'Bearer $accessToken';
    }
    _addTerminalHeaders(pedido);
    if (idempotencyKey?.isNotEmpty ?? false) {
      pedido.headers['Idempotency-Key'] = idempotencyKey!;
    }
    if (body != null) {
      pedido.headers['content-type'] = 'application/json';
      pedido.body = jsonEncode(body);
    }
    try {
      final transmitida = await _http.send(pedido).timeout(ApiClient._timeout);
      final resposta = await http.Response.fromStream(transmitida);
      return decodeApiResponse(resposta.statusCode, resposta.body);
    } on ApiException {
      rethrow;
    } catch (error) {
      throw ApiException(
        'A nuvem também não respondeu: $error',
        isConnectivity: true,
      );
    }
  }
}
