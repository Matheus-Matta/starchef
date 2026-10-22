/// O Esc que DESFAZ: a última coisa feita na tela sai primeiro.
///
/// Cada gesto reversível empilha como se desfaz (o pagamento adicionado, o
/// cupom aplicado, o item passado). O Esc tira do topo — do mais recente para
/// o mais antigo —, e só com a pilha da tela vazia volta a ser "voltar".
/// Antes o Esc no pagamento perguntava se descartava TODOS os recebimentos
/// montados: para tirar o crédito digitado errado, o caixa perdia os outros.
///
/// Cada entrada é de uma tela ('order', 'payment'): o Esc da venda nunca
/// desfaz o que foi feito no pagamento, e sair de uma tela esquece o dela.
class PilhaDeDesfazer {
  final _entradas = <_Entrada>[];

  /// Empilha como desfazer um gesto feito em [tela].
  void empilhar(String tela, String rotulo, void Function() desfazer) =>
      _entradas.add(_Entrada(tela, rotulo, desfazer));

  bool temEm(String tela) => _entradas.any((e) => e.tela == tela);

  /// Desfaz o gesto mais recente de [tela]; devolve o rótulo dele, ou `null`
  /// quando não havia nada a desfazer ali.
  String? desfazerUltimo(String tela) {
    for (var i = _entradas.length - 1; i >= 0; i--) {
      if (_entradas[i].tela != tela) continue;
      final entrada = _entradas.removeAt(i);
      entrada.desfazer();
      return entrada.rotulo;
    }
    return null;
  }

  /// A tela foi deixada: o que se fez nela não se desfaz mais pelo Esc.
  void esquecer(String tela) => _entradas.removeWhere((e) => e.tela == tela);

  void esquecerTudo() => _entradas.clear();
}

class _Entrada {
  const _Entrada(this.tela, this.rotulo, this.desfazer);

  final String tela;
  final String rotulo;
  final void Function() desfazer;
}
