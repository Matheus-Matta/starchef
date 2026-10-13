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
    // Vencidos os 5 minutos na nuvem, um ping decide se o terminal volta.
    await cloudFallback.conferirSeVenceu(
      () => ping(timeout: const Duration(seconds: 5)),
    );
    if (cloudFallback.irDiretoParaANuvem(path)) {
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
        afinidade.lembrar(resposta);
        return resposta;
      } on ApiException catch (erroDaNuvem) {
        // A nuvem também não atende: a loja pode ter voltado. Segue o caminho
        // normal, que tenta a loja primeiro.
        //
        // E a nuvem RECUSANDO A SESSÃO (401/403) também segue para a loja: o
        // token é da loja, assinado com a SECRET_KEY dela, e a nuvem nunca o
        // aceita. Repassar essa recusa mostrava "credenciais inválidas" ao
        // garçom logado, por até 5 minutos, em toda tela (comandas, mesas).
        if (!erroDaNuvem.isConnectivity && !_sessaoRecusada(erroDaNuvem)) {
          rethrow;
        }
      }
    }
    try {
      final resposta = await original();
      lastServerOrigin = ServerOrigin.loja;
      cloudFallback.localRespondeu();
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
          accessToken: accessToken,
          operationId: operationId,
        );
        lastServerOrigin = ServerOrigin.nuvem;
        return resposta;
      }
      if (!cloudFallback.deveTentar(method, path, erro)) rethrow;
      // CONFIRMA que a loja está fora antes de desviar. Um pacote perdido ou
      // um reinício de dois segundos do serviço não podem mudar o servidor do
      // terminal inteiro — muito menos para uma ESCRITA.
      final fora = await cloudFallback.confirmarQuedaDoLocal(
        () => ping(timeout: const Duration(seconds: 5)),
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
        afinidade.lembrar(resposta);
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

  /// A nuvem recusou o token: ele é da loja, e só ela o reconhece.
  static bool _sessaoRecusada(ApiException erro) =>
      erro.statusCode == 401 || erro.statusCode == 403;
}
