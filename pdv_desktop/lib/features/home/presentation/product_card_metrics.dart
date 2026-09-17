import 'dart:math' as math;

/// A medida do card de produto do catálogo.
///
/// Existe por uma razão só: a foto do produto é QUADRADA, e o quadrado depende
/// da largura que a coluna acabou tendo. Essa largura não é escolhida — ela cai
/// da conta que o `SliverGridDelegateWithMaxCrossAxisExtent` faz com o espaço
/// disponível. Um `mainAxisExtent` fixo acertaria o quadrado numa largura de
/// painel específica e erraria em todas as outras: a mesma foto sairia deitada
/// num monitor e em pé num notebook.
///
/// Então a conta da grade é refeita aqui, do lado de fora, para a altura do
/// card poder ser "a largura da foto mais o texto embaixo dela".
abstract final class ProductCardMetrics {
  /// Teto da largura de uma coluna. A largura real sai menor sempre que o
  /// espaço não divide redondo.
  ///
  /// É ELE QUE DIZ O TAMANHO DA FOTO: ela ocupa a largura inteira do card, e a
  /// altura sai daí pela proporção. Era 200, e nessa medida a foto respondia
  /// por dois terços da altura do card — o cardápio parecia um álbum, não uma
  /// lista de produtos para tocar.
  static const maxCardWidth = 160.0;

  /// A proporção da foto: a largura inteira do card, 80% disso de altura.
  ///
  /// Já foi 1:1. O quadrado resolveu a deformação — a foto vinha com um
  /// problema de decodificação que aparecia como esticão — mas deixou a imagem
  /// alta demais para o card: no lugar de uma foto de produto, uma placa. A
  /// largura ficou como estava; só a altura desceu para 80%.
  static const photoHeightFactor = .8;
  static const photoAspect = 1 / photoHeightFactor;

  static const spacing = 8.0;

  /// O que fica embaixo da foto: nome em até duas linhas, código, categoria e
  /// a linha de preço com o botão de adicionar.
  ///
  /// É o PIOR caso: nome nas duas linhas. E é um número que só pode existir
  /// porque nada aí embaixo quebra por largura — nome, código e categoria têm
  /// limite de linhas, e o preço virou uma linha só. Enquanto isso valer, a
  /// altura do texto não muda com a largura da coluna e a foto fecha quadrada
  /// em qualquer painel; se algum desses voltar a quebrar, o teste acusa.
  static const textHeight = 104.0;

  /// A largura de uma coluna, pela mesma conta que o delegate do Flutter faz.
  ///
  /// Repetir a conta é o preço de saber a largura antes de a grade existir. Se
  /// ela mudar do lado do Flutter, a foto deixa de fechar quadrada — e é isso
  /// que o teste verifica.
  static double cardWidth(double available) {
    if (available <= 0) return maxCardWidth;
    final columns = math
        .max(1, (available / (maxCardWidth + spacing)).ceil())
        .toInt();
    return (available - spacing * (columns - 1)) / columns;
  }

  /// Altura do card: a foto na proporção dela, mais o texto.
  static double photoHeightFor(double cardWidth) =>
      cardWidth * photoHeightFactor;

  static double cardHeight(double available) =>
      photoHeightFor(cardWidth(available)) + textHeight;
}
