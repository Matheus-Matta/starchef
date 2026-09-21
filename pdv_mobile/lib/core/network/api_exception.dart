/// Falha de uma chamada ao backend ou ao backend.
///
/// [isConnectivity] separa "não cheguei no servidor" de "o servidor recusou":
/// a tela trata os dois de formas diferentes — a primeira sugere conferir a
/// rede, a segunda mostra o motivo que veio do servidor.
class ApiException implements Exception {
  const ApiException(
    this.message, {
    this.statusCode,
    this.isConnectivity = false,
    this.reachedServer = false,
  });

  final String message;
  final int? statusCode;
  final bool isConnectivity;

  /// A requisição PODE ter chegado ao servidor e sido executada.
  ///
  /// É a diferença entre "conexão recusada" e "tempo esgotado", e ela decide
  /// se a escrita pode ser repetida em OUTRO backend. Conexão recusada
  /// significa que ninguém recebeu nada: repetir é seguro. Tempo esgotado
  /// significa que o servidor pode ter gravado e só a resposta se perdeu —
  /// repetir na nuvem cobraria o cliente duas vezes, porque a deduplicação por
  /// `Idempotency-Key` vive no banco de CADA backend.
  ///
  /// Na dúvida, o valor é `true`: é melhor a escrita esperar na fila do que
  /// virar uma segunda venda.
  final bool reachedServer;

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => message;
}
