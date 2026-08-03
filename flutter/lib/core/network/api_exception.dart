class ApiException implements Exception {
  const ApiException(
    this.message, {
    this.statusCode,
    this.isConnectivity = false,
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

  @override
  String toString() => message;
}
