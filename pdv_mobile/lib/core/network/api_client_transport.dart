part of 'api_client.dart';

/// O TRANSPORTE: montar a requisição, mandar e traduzir a falha.
///
/// Separado das regras de desvio (`api_client_fallback.dart`) porque são dois
/// assuntos com ritmos diferentes: isto aqui muda quando o HTTP muda; lá muda
/// quando a política de duas pontas muda. E é lá que moram as regras que
/// impedem a venda duplicada — elas precisam ser lidas juntas.
extension ApiClientTransport on ApiClient {
  Future<Map<String, dynamic>> _requestNaLoja(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    String? idempotencyKey,
  }) async {
    final explicitToken = accessToken != null;
    try {
      return await _send(
        method,
        path,
        query: query,
        body: body,
        token: accessToken ?? _accessToken,
        idempotencyKey: idempotencyKey,
      );
    } on ApiException catch (error) {
      final canRefresh =
          error.statusCode == 401 &&
          !explicitToken &&
          !path.startsWith('/auth/') &&
          (_refreshToken?.isNotEmpty ?? false);
      if (!canRefresh || !await _refresh()) rethrow;
      return _send(
        method,
        path,
        query: query,
        body: body,
        token: _accessToken,
        idempotencyKey: idempotencyKey,
      );
    }
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? token,
    String? idempotencyKey,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
    );
    final request = http.Request(method, uri)
      ..headers['accept'] = 'application/json';
    if (token?.isNotEmpty ?? false) {
      request.headers['authorization'] = 'Bearer $token';
    }
    if (_terminalId?.isNotEmpty ?? false) {
      request.headers['X-Terminal-Id'] = _terminalId!;
      request.headers['X-Terminal-Name'] = 'PDV Mobile';
    }
    if (idempotencyKey?.isNotEmpty ?? false) {
      request.headers['Idempotency-Key'] = idempotencyKey!;
    }
    if (body != null) {
      request.headers['content-type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    try {
      final streamed = await _http.send(request).timeout(ApiClient._timeout);
      final response = await http.Response.fromStream(streamed);
      return decodeApiResponse(response.statusCode, response.body);
    } on TimeoutException {
      // PODE ter chegado e sido executada — só a resposta não voltou. É a
      // única falha de rede em que repetir num outro backend é perigoso.
      throw const ApiException(
        'O servidor demorou demais para responder.',
        isConnectivity: true,
        reachedServer: true,
      );
    } on SocketException catch (error) {
      throw ApiException(
        'Sem conexão com o servidor (${error.message}).',
        isConnectivity: true,
      );
    } on http.ClientException catch (error) {
      throw ApiException(error.message, isConnectivity: true);
    }
  }
}
