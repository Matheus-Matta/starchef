class ApiException implements Exception {
  const ApiException(
    this.message, {
    this.statusCode,
    this.isConnectivity = false,
    this.reachedServer = false,
    this.retryAfter,
    this.code,
    this.data = const {},
  });

  final String message;
  final int? statusCode;

  /// O código da recusa (`error.code` do envelope), ex.: `comanda_ja_cobrada`.
  ///
  /// Com ele a tela pode AGIR em vez de mostrar o erro: abrir a conta onde a
  /// comanda está, abrir o pedido já pago (`home_page_conflitos.dart`).
  final String? code;

  /// O resto do `error` que veio com o código — o pedido de destino, os totais.
  final Map<String, dynamic> data;

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

  /// O servidor recusou a CREDENCIAL — só isso justifica apagar o login.
  ///
  /// 429 e 5xx dizem que o servidor não pôde atender agora, não que o token é
  /// ruim. Depois de reiniciar o PC o PDV abre antes de o backend terminar de
  /// subir, e tratar o 502 do proxy como recusa obrigava a logar de novo.
  bool get isCredentialRefused => statusCode == 401;

  @override
  String toString() => message;
}

/// O `error.code` do envelope da API, ou `null`.
String? codigoDoErro(Map<String, dynamic>? corpo) {
  final erro = corpo?['error'];
  if (erro is! Map) return null;
  final codigo = erro['code'];
  return codigo is String && codigo.isNotEmpty ? codigo : null;
}

/// O resto do `error` do envelope (sem `code` e `message`).
Map<String, dynamic> dadosDoErro(Map<String, dynamic>? corpo) {
  final erro = corpo?['error'];
  if (erro is! Map) return const {};
  return {
    for (final MapEntry(:key, :value) in erro.entries)
      if (key != 'code' && key != 'message') '$key': value,
  };
}
