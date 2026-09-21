class ApiException implements Exception {
  const ApiException(
    this.message, {
    this.statusCode,
    this.isConnectivity = false,
    this.reachedServer = false,
    this.retryAfter,
  });

  final String message;
  final int? statusCode;

  /// A falha foi de conectividade, não uma recusa do servidor.
  ///
  /// A interface trata esses dois casos de formas diferentes: uma recusa é um
  /// alerta que o operador precisa ler e resolver, enquanto a falta de rede é
  /// um estado contínuo — já sinalizado pelo indicador de conexão — que não
  /// pode virar um alerta novo a cada chamada.
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

  /// Quanto o servidor pediu para esperar antes de tentar de novo (429/503).
  ///
  /// Quem insiste — a fila da impressora, uma espera por autorização fiscal —
  /// precisa deste número para não cair na MESMA janela de novo com uma escada
  /// de backoff mais curta que o prazo pedido. `null` quando o servidor não
  /// deu prazo: aí quem recebe decide o próprio.
  final Duration? retryAfter;

  @override
  String toString() => message;
}
