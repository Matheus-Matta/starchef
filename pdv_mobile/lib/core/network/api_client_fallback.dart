part of 'api_client.dart';

/// O desvio para a nuvem: quando acontece, e com que garantias.
///
/// Fica separado do cliente porque é um assunto com regras próprias — e são
/// regras que impedem a venda duplicada, não detalhes de transporte. Quem for
/// mexer nelas precisa lê-las juntas, não espalhadas no meio do HTTP.
extension ApiClientFallback on ApiClient {
  /// Tenta a loja; se ela estiver CONFIRMADAMENTE fora, repete na nuvem.
  ///
  /// Mesmas regras do PDV desktop, e de propósito: os dois terminais falam com
  /// os mesmos dois backends, e duas políticas diferentes de desvio seriam
  /// duas chances diferentes de duplicar a mesma venda.
  Future<Map<String, dynamic>> _comPlanoB(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    String? idempotencyKey,
  }) async {
    if (cloudFallback.irDiretoParaANuvem(path)) {
      try {
        final resposta = await _naNuvem(
          method,
          path,
          query: query,
          body: body,
          accessToken: accessToken ?? _accessToken,
          idempotencyKey: idempotencyKey,
        );
        lastServerOrigin = ServerOrigin.nuvem;
        afinidade.lembrar(resposta);
        return resposta;
      } on CobrarNaLoja {
        // A loja está no ar (a nuvem sabe pelo sync): a janela acabou.
        cloudFallback.localRespondeu();
      } on ApiException catch (erroDaNuvem) {
        // A nuvem também não atende: a loja pode ter voltado. Segue o caminho
        // normal, que tenta a loja primeiro.
        if (!erroDaNuvem.isConnectivity) rethrow;
      }
    }
    try {
      final resposta = await _requestNaLoja(
        method,
        path,
        query: query,
        body: body,
        accessToken: accessToken,
        idempotencyKey: idempotencyKey,
      );
      cloudFallback.localRespondeu();
      lastServerOrigin = ServerOrigin.loja;
      return resposta;
    } on ApiException catch (erro) {
      if (erro.statusCode == 404 &&
          !cloudFallback.nuncaDesvia(path) &&
          afinidade.tocaNaNuvem(path)) {
        // Nasceu na nuvem e ainda não desceu: a loja não executou nada.
        final resposta = await _naNuvem(
          method,
          path,
          query: query,
          body: body,
          accessToken: accessToken ?? _accessToken,
          idempotencyKey: idempotencyKey,
        );
        lastServerOrigin = ServerOrigin.nuvem;
        return resposta;
      }
      if (!cloudFallback.deveTentar(method, path, erro)) rethrow;
      final fora = await cloudFallback.confirmarQuedaDoLocal(_lojaResponde);
      if (!fora) rethrow;
      try {
        final resposta = await _naNuvem(
          method,
          path,
          query: query,
          body: body,
          accessToken: accessToken ?? _accessToken,
          // A MESMA chave da tentativa na loja: é ela que, depois, faz a loja
          // reconhecer a operação que a nuvem executou — o registro de
          // idempotência desce pela sincronização.
          idempotencyKey: idempotencyKey,
        );
        lastServerOrigin = ServerOrigin.nuvem;
        afinidade.lembrar(resposta);
        return resposta;
      } on CobrarNaLoja {
        rethrow;
      } on ApiException {
        // A nuvem também não atendeu. Propaga o erro DA LOJA: é nela que o
        // garçom pode agir, e é o erro dela que carrega o código e o prazo que
        // as telas leem.
        throw erro;
      }
    }
  }

  /// A loja está de pé? Prazo CURTO: a pergunta é "tem alguém aí?".
  Future<bool> _lojaResponde() async {
    try {
      final uri = Uri.parse(
        '${baseUrl.replaceFirst(RegExp(r'/api/v\d+/?$'), '')}/health/',
      );
      final resposta = await _http.get(uri).timeout(const Duration(seconds: 3));
      return resposta.statusCode >= 200 && resposta.statusCode < 500;
    } catch (_) {
      return false;
    }
  }

  /// A requisição repetida contra a nuvem, com a MESMA chave de idempotência.
  Future<Map<String, dynamic>> _naNuvem(
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
      if (resposta.statusCode == 409 &&
          resposta.body.contains(CobrarNaLoja.codigo)) {
        throw CobrarNaLoja(
          extractApiDetail(jsonDecode(resposta.body) as Map<String, dynamic>),
        );
      }
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
