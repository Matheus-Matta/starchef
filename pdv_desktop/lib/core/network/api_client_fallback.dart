part of 'api_client.dart';

/// O desvio para a nuvem: quando acontece, e com que garantias.
///
/// Fica separado do cliente porque é um assunto com regras próprias — e são
/// regras que impedem a venda duplicada, não detalhes de transporte. Quem for
/// mexer nelas precisa lê-las juntas, não espalhadas no meio do HTTP.
///
/// É o irmão de `api_client_fallback.dart` do PDV mobile, e as duas políticas
/// são iguais de propósito: os dois terminais falam com os mesmos dois
/// backends, e duas regras diferentes de desvio seriam duas chances diferentes
/// de duplicar a mesma venda.
extension ApiClientFallback on ApiClient {
  /// Tenta a loja; se ela estiver CONFIRMADAMENTE fora, repete na nuvem.
  ///
  /// Leitura e escrita desviam — o salão não para porque a máquina da loja
  /// caiu. O que não desvia é a escrita cuja resposta se PERDEU (tempo
  /// esgotado): a loja pode tê-la gravado, e repetir na nuvem cobraria de
  /// novo, porque a chave que a loja consumiu a nuvem nunca viu. Essa espera
  /// na fila, que reenvia para a MESMA loja com a mesma chave.
  ///
  /// Quem decide isso é [CloudFallback.deveTentar]; as regras estão lá, com um
  /// teste para cada uma.
  Future<Map<String, dynamic>> _comPlanoB(
    String method,
    String path, {
    required Future<Map<String, dynamic>> Function() original,
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    String? operationId,
  }) async {
    try {
      final resposta = await original();
      lastServerOrigin = ServerOrigin.loja;
      cloudFallback.localRespondeu();
      return resposta;
    } on ApiException catch (erro) {
      if (!cloudFallback.deveTentar(method, path, erro)) rethrow;
      // CONFIRMA que a loja está fora antes de desviar. Um pacote perdido ou
      // um reinício de dois segundos do serviço não podem mudar o servidor do
      // terminal inteiro — muito menos para uma ESCRITA.
      final fora = await cloudFallback.confirmarQuedaDoLocal(
        () => ping(timeout: const Duration(seconds: 3)),
      );
      if (!fora) rethrow;
      try {
        final resposta = await _naNuvem(
          method,
          path,
          query: query,
          body: body,
          accessToken: accessToken,
          operationId: operationId,
        );
        lastServerOrigin = ServerOrigin.nuvem;
        _publishStatus(NetworkPhase.cloud);
        return resposta;
      } on ApiException {
        // A nuvem também não atendeu. Propaga o erro DA LOJA, não o da nuvem:
        // é na loja que o operador pode agir (a máquina, o cabo, o serviço), e
        // é o erro dela que carrega o prazo de espera e o código que as telas
        // leem. Trocar por "a nuvem também não respondeu" apagaria tudo isso.
        throw erro;
      }
    }
  }

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
  Future<Map<String, dynamic>> _naNuvem(
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
    try {
      final pedido = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) pedido.body = jsonEncode(body);
      final transmitida = await _client.send(pedido).timeout(requestTimeout);
      final resposta = await http.Response.fromStream(transmitida);
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
