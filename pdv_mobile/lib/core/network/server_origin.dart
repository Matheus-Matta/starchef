/// QUAL SERVIDOR respondeu — a loja ou a nuvem.
///
/// A tela precisa dizer isso ao operador: o que ele está lendo da nuvem pode
/// estar atrás do que a loja tem, e o que ele lançar não aparece ali até a
/// sincronização rodar. Um dado de outra origem sem aviso é pior que tela
/// vazia — ele parece atual.
enum ServerOrigin {
  /// O backend da loja respondeu. É o caminho normal.
  loja,

  /// A loja não respondeu e a nuvem atendeu no lugar.
  nuvem,
}
