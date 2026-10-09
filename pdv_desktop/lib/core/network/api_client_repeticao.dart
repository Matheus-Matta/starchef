part of 'api_client.dart';

/// As duas regras que impedem a escrita em dobro quando a rede falha.
///
/// Ficam juntas e separadas do desvio (`api_client_fallback.dart`) porque
/// respondem a mesma pergunta — "esta tentativa é a mesma operação?" — e as
/// duas precisam levar a MESMA `Idempotency-Key` para o servidor reconhecer.
extension ApiClientRepeticao on ApiClient {
  /// A escrita cuja resposta se perdeu é repetida UMA vez, com a MESMA chave.
  ///
  /// Tempo esgotado numa escrita é o caso em que o servidor PODE ter gravado.
  /// Devolver o erro ao operador fazia ele repetir o gesto — e o gesto novo
  /// sai com chave nova, que o servidor não reconhece: o item lançado duas
  /// vezes, achado pela simulação do dia a dia. Repetindo aqui com a mesma
  /// chave, o servidor devolve a resposta que já deu (ou executa, se a
  /// primeira não chegou). Só quando a loja responde ao `/health/`: com ela
  /// fora, a repetição só esperaria outro tempo esgotado.
  Future<Map<String, dynamic>> _repetirSeAPerdeu(
    String method,
    Future<Map<String, dynamic>> Function() tentativa,
  ) async {
    try {
      return await tentativa();
    } on ApiException catch (erro) {
      if (method == 'GET' || !erro.reachedServer) rethrow;
      if (!await ping(timeout: const Duration(seconds: 3))) rethrow;
      return tentativa();
    }
  }

  /// Guarda a chave da escrita que falhou na rede; esquece no sucesso.
  /// Ver `chaves_de_repeticao.dart`.
  Future<Map<String, dynamic>> _comChaveLembrada(
    String? assinatura,
    String? operationId,
    Future<Map<String, dynamic>> Function() chamada,
  ) async {
    try {
      final resposta = await chamada();
      if (assinatura != null) repeticoes.esquecer(assinatura);
      return resposta;
    } on ApiException catch (erro) {
      final naRede = erro.isConnectivity || erro.reachedServer;
      if (assinatura != null && operationId != null && naRede) {
        repeticoes.guardar(assinatura, operationId);
      }
      rethrow;
    }
  }
}
