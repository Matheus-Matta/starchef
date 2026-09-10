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
  /// Sem isto, um 429 relayado por um Caixa Secundário perdia o prazo real em
  /// cada tradução que sofria no caminho (nuvem → principal → secundário) e
  /// chegava a quem enfileira como "falha, tente de novo" sem número nenhum —
  /// que então reinsistia pela própria escada de backoff, mais curta que o
  /// prazo pedido, e caía na MESMA janela de novo. `null` quando o servidor
  /// não deu prazo nenhum: quem recebe decide o próprio backoff.
  final Duration? retryAfter;

  @override
  String toString() => message;
}
