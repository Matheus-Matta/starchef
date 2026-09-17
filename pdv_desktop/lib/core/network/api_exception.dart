class ApiException implements Exception {
  const ApiException(
    this.message, {
    this.statusCode,
    this.isConnectivity = false,
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
