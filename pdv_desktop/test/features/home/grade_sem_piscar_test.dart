import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/grade_de_produtos.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_catalog_tile.dart';

/// O destaque das setas passa pelos cartões SEM recriá-los.
///
/// O cartão destacado ganhava um embrulho a mais; a árvore mudava a cada seta,
/// o cartão era recriado e a imagem do produto piscava recarregando.
void main() {
  Widget grade(int destacado) => MaterialApp(
    home: Scaffold(
      body: SizedBox(
        width: 900,
        height: 600,
        child: GradeDeProdutos(
          products: [
            for (var n = 0; n < 4; n++)
              {'id': 'p$n', 'name': 'Prato $n', 'current_price': '10.00'},
          ],
          money: (valor) => '$valor',
          onProductPressed: (_) {},
          destacado: destacado,
        ),
      ),
    ),
  );

  testWidgets('trocar o destaque mantém os mesmos cartões', (tester) async {
    await tester.pumpWidget(grade(0));
    final antes = tester.elementList(find.byType(ProductCatalogTile)).toList();

    await tester.pumpWidget(grade(1));
    await tester.pumpAndSettle();
    final depois = tester.elementList(find.byType(ProductCatalogTile)).toList();

    expect(depois, hasLength(antes.length));
    for (var n = 0; n < antes.length; n++) {
      expect(identical(depois[n], antes[n]), isTrue, reason: 'cartão $n');
    }
    final destacados = tester
        .widgetList<ProductCatalogTile>(find.byType(ProductCatalogTile))
        .map((cartao) => cartao.destacado)
        .toList();
    expect(destacados, [false, true, false, false]);
  });
}
