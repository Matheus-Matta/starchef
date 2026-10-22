import 'product_card_metrics.dart';

/// O produto em destaque na grade da venda, andado pelas setas.
///
/// As setas andam pela GRADE de produtos e o Espaço adiciona o destacado: dá
/// para vender só pelo teclado sem digitar o nome. ← → andam um, ↑ ↓ andam
/// uma linha inteira, e as bordas seguram (não dão a volta: no fim da grade o
/// destaque fica no último, em vez de pular para o primeiro sem o caixa ver).
enum SetaDaGrade { esquerda, direita, cima, baixo }

/// O índice do próximo destaque; `null` com a grade vazia.
///
/// Sem destaque ainda, qualquer seta começa no primeiro produto.
int? moverDestaque({
  required int? atual,
  required int total,
  required int colunas,
  required SetaDaGrade seta,
}) {
  if (total <= 0) return null;
  if (atual == null || atual < 0 || atual >= total) return 0;
  final passo = switch (seta) {
    SetaDaGrade.esquerda => -1,
    SetaDaGrade.direita => 1,
    SetaDaGrade.cima => -colunas,
    SetaDaGrade.baixo => colunas,
  };
  final proximo = atual + passo;
  if (proximo < 0 || proximo >= total) {
    // ↑ na primeira linha e ↓ na última: fica onde está.
    return seta == SetaDaGrade.cima || seta == SetaDaGrade.baixo
        ? atual
        : proximo.clamp(0, total - 1);
  }
  return proximo;
}

/// Quantas colunas a grade desenha nesta largura: a MESMA conta do
/// `SliverGridDelegateWithMaxCrossAxisExtent` que a monta.
int colunasDaGrade(double larguraUtil) {
  final colunas =
      (larguraUtil /
              (ProductCardMetrics.maxCardWidth + ProductCardMetrics.spacing))
          .ceil();
  return colunas < 1 ? 1 : colunas;
}
