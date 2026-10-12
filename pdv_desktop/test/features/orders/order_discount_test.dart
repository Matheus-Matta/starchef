import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_catalog_panel.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/order_discount_field.dart';

/// Os centavos do desconto (digitado na tela de pagamento) e a venda nova
/// zerada. O campo de desconto do CARRINHO saiu: o desconto se decide no
/// pagamento, junto da taxa e do CPF/CNPJ.
void main() {
  group('centavos', () {
    test('cada dígito entra pelos centavos, como no teclado de pagamento', () {
      expect(centavosDigitados('5'), 5);
      expect(centavosDigitados('500'), 500);
      expect(centavosDigitados('R\$ 1.234,50'), 123450);
      expect(centavosDigitados('abc'), 0);
      expect(centavosDigitados(''), 0);
      // Tecla presa não vira um desconto de bilhões.
      expect(centavosDigitados('99999999999999'), 999999999);
    });

    test('mostra no formato do caixa e manda no formato da API', () {
      expect(formatarCentavos(0), '0,00');
      expect(formatarCentavos(500), '5,00');
      expect(formatarCentavos(123450), '1.234,50');
      expect(centavosParaApi(123450), '1234.50');
      expect(centavosParaApi(5), '0.05');
    });
  });

  testWidgets('venda nova recria a busca do catálogo vazia', (tester) async {
    Widget catalogo(int geracao) => MaterialApp(
      home: Scaffold(
        body: ProductCatalogPanel(
          products: const [],
          allProducts: const [],
          categories: const [],
          selectedCategory: null,
          search: '',
          searchGeneration: geracao,
          money: (v) => '$v',
          onSearchChanged: (_) {},
          onCategoryChanged: (_) {},
          onProductPressed: (_) {},
        ),
      ),
    );
    await tester.pumpWidget(catalogo(0));
    await tester.enterText(find.byType(TextField).first, 'arroz');
    expect(find.text('arroz'), findsOneWidget);

    await tester.pumpWidget(catalogo(1));

    expect(find.text('arroz'), findsNothing);
  });
}
