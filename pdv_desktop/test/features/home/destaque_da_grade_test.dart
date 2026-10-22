import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/destaque_da_grade.dart';

/// As setas da venda andam pela grade de produtos.
void main() {
  int? mover(int? atual, SetaDaGrade seta, {int total = 10, int colunas = 4}) =>
      moverDestaque(atual: atual, total: total, colunas: colunas, seta: seta);

  test('a primeira seta começa no primeiro produto', () {
    expect(mover(null, SetaDaGrade.baixo), 0);
    expect(mover(null, SetaDaGrade.direita), 0);
  });

  test('esquerda e direita andam um; cima e baixo, uma linha', () {
    expect(mover(5, SetaDaGrade.direita), 6);
    expect(mover(5, SetaDaGrade.esquerda), 4);
    expect(mover(5, SetaDaGrade.baixo), 9);
    expect(mover(5, SetaDaGrade.cima), 1);
  });

  test('as bordas seguram em vez de dar a volta', () {
    expect(mover(0, SetaDaGrade.esquerda), 0);
    expect(mover(9, SetaDaGrade.direita), 9);
    expect(mover(1, SetaDaGrade.cima), 1);
    expect(mover(7, SetaDaGrade.baixo), 7);
  });

  test('grade vazia não tem destaque', () {
    expect(mover(null, SetaDaGrade.baixo, total: 0), isNull);
  });

  test('a conta de colunas é a da grade', () {
    expect(colunasDaGrade(1), 1);
    expect(colunasDaGrade(0), 1);
  });
}
