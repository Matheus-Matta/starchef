import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/commands/data/linhas_da_comanda.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/linha_da_comanda_tile.dart';

void main() {
  test('linha em branco vai sempre para o fim, como sai no papel', () {
    final linhas = emOrdemDeImpressao([
      const LinhaDaComanda.emBranco(),
      const LinhaDaComanda.produto('a'),
      const LinhaDaComanda.produto('b'),
    ]);

    expect(linhas.map((l) => l.produtoId), ['a', 'b', null]);
  });

  test(
    'o JSON da API vira linha e volta igual; tipo desconhecido é ignorado',
    () {
      final lidas = [
        {'tipo': 'produto', 'produto': 'p1'},
        {'tipo': 'branco'},
        {'tipo': 'bebida'},
      ].map(LinhaDaComanda.fromJson).whereType<LinhaDaComanda>().toList();

      expect(lidas.map((l) => l.toJson()), [
        {'tipo': 'produto', 'produto': 'p1'},
        {'tipo': 'branco'},
      ]);
    },
  );

  testWidgets(
    'nome comprido é cortado e não empurra os três quadrados para fora',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 360,
              child: LinhaDaComandaTile(
                nome: 'Refrigerante Coca-Cola Lata 350ml Zero Açúcar ' * 4,
                onRemover: () {},
              ),
            ),
          ),
        ),
      );

      // Overflow de layout vira exceção no teste: o Row não pode estourar.
      expect(tester.takeException(), isNull);
      final texto = tester.widget<Text>(find.byType(Text));
      expect(texto.overflow, TextOverflow.ellipsis);
      expect(texto.maxLines, 1);
    },
  );
}
