/// Falha de uma chamada ao backend ou ao Caixa Principal.
///
/// [isConnectivity] separa "não cheguei no servidor" de "o servidor recusou":
/// a tela trata os dois de formas diferentes — a primeira sugere conferir a
/// rede, a segunda mostra o motivo que veio do servidor.
class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.isConnectivity = false});

  final String message;
  final int? statusCode;
  final bool isConnectivity;

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => message;
}
