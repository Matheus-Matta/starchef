import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_catalog_panel.dart';

/// O Enter dentro da busca da venda CONCLUI a busca: o cursor sai do campo e
/// as setas, o Espaço e o Enter voltam a ser da venda.
///
/// Ele adicionava o primeiro produto da grade — um prato que ninguém pediu.
/// Quem adiciona é o Espaço; fora da busca, o Enter vai ao pagamento.
void main() {
  testWidgets('Enter na busca tira o cursor e não adiciona nada', (
    tester,
  ) async {
    final adicionados = <String>[];
    final foco = FocusNode();
    addTearDown(foco.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProductCatalogPanel(
            products: const [
              {'id': 'p1', 'name': 'Prato feito', 'sale_price': '25.00'},
            ],
            allProducts: const [
              {'id': 'p1', 'name': 'Prato feito', 'sale_price': '25.00'},
            ],
            categories: const [],
            selectedCategory: null,
            search: 'prato',
            money: (valor) => '$valor',
            onSearchChanged: (_) {},
            onCategoryChanged: (_) {},
            onProductPressed: (produto) => adicionados.add('${produto['id']}'),
            searchFocusNode: foco,
          ),
        ),
      ),
    );
    foco.requestFocus();
    await tester.pump();
    expect(foco.hasFocus, isTrue);

    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();

    expect(foco.hasFocus, isFalse);
    expect(adicionados, isEmpty);
  });
}
