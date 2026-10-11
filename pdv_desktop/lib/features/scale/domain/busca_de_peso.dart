/// Quando pedir o peso à balança sem ninguém apertar "Pedir peso".
///
/// Voltar para a tela de pesagem zera o peso exibido. A balança que só
/// transmite quando o peso MUDA não manda nada se o prato continua parado em
/// cima dela — e a tela ficava em 0 kg com o prato ali. Sem amostra por
/// [espera], o peso é pedido; a que transmite sem parar nunca chega a isso.
class BuscaDePeso {
  BuscaDePeso({
    this.espera = const Duration(seconds: 1),
    this.maximoDePedidos = 3,
  });

  final Duration espera;

  /// Balança que não responde (porta só de leitura) não é cutucada para
  /// sempre: o operador ainda tem o botão e o peso manual.
  final int maximoDePedidos;

  /// O peso na tela ainda não é confiável: zerado pela volta, ou chegou
  /// oscilando e parou de chegar. Zero INFORMADO pela balança é vazio de
  /// verdade e não precisa de nova consulta.
  bool _emAberto = true;
  DateTime? _desde;
  int _pedidos = 0;

  /// A tela voltou para o início: o peso exibido foi zerado sem leitura.
  void recomecar() {
    _emAberto = true;
    _desde = null;
    _pedidos = 0;
  }

  /// Chegou uma amostra. [conhecido] = vazio, ou estável, ou o prato lançado.
  void amostra(DateTime em, {required bool conhecido}) {
    _emAberto = !conhecido;
    _desde = em;
  }

  /// Chamado a cada segundo com a estação esperando peso.
  bool devePedir(DateTime agora) {
    if (!_emAberto || _pedidos >= maximoDePedidos) return false;
    final desde = _desde ??= agora;
    if (agora.difference(desde) < espera) return false;
    _pedidos++;
    _desde = agora;
    return true;
  }
}
