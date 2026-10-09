/// Por quanto tempo o terminal fica na nuvem depois de a loja cair.
///
/// Uma janela FIXA de 30 segundos fazia a loja instável — o serviço que
/// reinicia, a rede que falha a cada minuto — arrastar o terminal de um
/// servidor para o outro o tempo todo: a tela piscava "loja"/"nuvem" e o mesmo
/// pedido era editado nos dois com segundos de diferença.
///
/// Agora a janela CRESCE quando a loja cai de novo logo depois de voltar:
/// 30 s, 1 min, 2 min, 4 min, até 5 min. Uma loja que fica de pé por
/// [estabilidade] zera a contagem, e a próxima queda volta aos 30 s.
class VereditoDaLoja {
  VereditoDaLoja({DateTime Function()? relogio})
    : _agora = relogio ?? DateTime.now;

  static const janelaBase = Duration(seconds: 30);
  static const teto = Duration(minutes: 5);

  /// Quanto tempo de pé a loja precisa ficar para a próxima queda contar
  /// como nova, e não como recaída.
  static const estabilidade = Duration(minutes: 5);

  final DateTime Function() _agora;
  DateTime? _foraDesde;
  DateTime? _voltouEm;
  bool _estavaFora = false;
  int _recaidas = 0;

  /// A janela que vale para a queda atual.
  Duration get janela {
    final segundos = janelaBase.inSeconds << _recaidas.clamp(0, 4);
    return segundos >= teto.inSeconds ? teto : Duration(seconds: segundos);
  }

  /// A loja está confirmadamente fora AGORA?
  bool get localForaDoAr {
    final desde = _foraDesde;
    if (desde == null) return false;
    if (_agora().difference(desde) > janela) {
      _foraDesde = null;
      return false;
    }
    return true;
  }

  /// A loja respondeu. Se ela estava fora, marca a volta.
  void localRespondeu() {
    if (_estavaFora) {
      _voltouEm = _agora();
      _estavaFora = false;
    }
    _foraDesde = null;
  }

  /// A loja foi confirmada fora. Caiu logo depois de voltar? É recaída.
  void marcarForaDoAr() {
    final agora = _agora();
    final voltou = _voltouEm;
    final recaiu = voltou != null && agora.difference(voltou) < estabilidade;
    _recaidas = recaiu ? _recaidas + 1 : 0;
    _foraDesde = agora;
    _estavaFora = true;
  }
}
