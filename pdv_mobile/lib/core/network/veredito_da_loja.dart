/// Por quanto tempo o terminal fica na nuvem depois de a loja cair.
///
/// Caiu, FICA: [janela] de 5 minutos na nuvem, para o operador terminar o que
/// estava fazendo num servidor só. Antes a janela começava em 30 s e qualquer
/// resposta da loja a desfazia — fechar comanda tentava a loja primeiro —, e
/// o terminal pulava de servidor no meio de uma venda: metade dela ia para
/// cada lado.
///
/// Vencida a janela, o terminal NÃO volta sozinho: a próxima requisição faz um
/// ping na loja antes ([precisaConferir], `CloudFallback.conferirSeVenceu`).
/// Respondeu, volta; não respondeu, mais 5 minutos na nuvem.
class VereditoDaLoja {
  VereditoDaLoja({DateTime Function()? relogio})
    : _agora = relogio ?? DateTime.now;

  static const janela = Duration(minutes: 5);

  final DateTime Function() _agora;
  DateTime? _foraDesde;

  /// O terminal está na nuvem (dentro da janela, ou esperando o ping)?
  bool get localForaDoAr => _foraDesde != null;

  /// A janela venceu: antes da próxima requisição, um ping decide.
  bool get precisaConferir {
    final desde = _foraDesde;
    return desde != null && _agora().difference(desde) >= janela;
  }

  /// A loja respondeu (fiscal e caixa, que nunca desviam, falam com ela).
  ///
  /// Dentro da janela isso NÃO traz o terminal de volta: só o ping depois dos
  /// 5 minutos traz. Fora da janela, confirma a loja.
  void localRespondeu() {
    if (_foraDesde != null && !precisaConferir) return;
    _foraDesde = null;
  }

  /// A loja foi confirmada fora: 5 minutos na nuvem, a contar de agora.
  void marcarForaDoAr() => _foraDesde = _agora();

  /// O ping depois da janela respondeu: o terminal volta para a loja.
  void voltou() => _foraDesde = null;
}
