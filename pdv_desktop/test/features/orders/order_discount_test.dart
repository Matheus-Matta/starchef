import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_catalog_panel.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/order_cart_panel.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/order_discount_field.dart';

/// Desconto digitado direto no resumo do pedido, e a venda nova zerada.
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

    test('o desconto fica preso ao pedido em que foi digitado', () {
      final desconto = TypedDiscount()..definir('pedido-1', 1500);

      expect(desconto.valorDe('pedido-1'), 1500);
      expect(
        desconto.valorDe('pedido-2'),
        isNull,
        reason: 'outro pedido não herda',
      );
      expect(desconto.valorDe(null), isNull);
      desconto.limpar();
      expect(desconto.valorDe('pedido-1'), isNull);
    });
  });

  Widget carrinho({int? desconto, ValueChanged<int>? aoMudar}) => MaterialApp(
    home: ShadTheme(
      data: AppTheme.shadLight(),
      child: Scaffold(
        body: SizedBox(
          width: 420,
          height: 900,
          child: OrderCartPanel(
            order: const {
              'id': 'p1',
              'subtotal': '100.00',
              'discount': '0.00',
              'total': '100.00',
            },
            table: null,
            customer: null,
            printing: false,
            items: const [],
            money: (v) => 'R\$ $v',
            onVoidItem: (_) {},
            onFinish: () {},
            onSendToKitchen: () {},
            onPrint: () {},
            discountCents: desconto,
            onDiscountChanged: aoMudar,
          ),
        ),
      ),
    ),
  );

  testWidgets('digitar o desconto avisa o valor e o total da tela acompanha', (
    tester,
  ) async {
    final digitados = <int>[];
    await tester.pumpWidget(carrinho(aoMudar: digitados.add));

    await tester.enterText(find.byKey(const Key('order-discount')), '1500');
    expect(digitados.last, 1500);

    await tester.pumpWidget(carrinho(desconto: 1500, aoMudar: digitados.add));
    expect(find.text('15,00'), findsOneWidget);
    expect(find.text('R\$ 85.0'), findsOneWidget);
  });

  testWidgets('desconto acima do subtotal avisa no campo', (tester) async {
    await tester.pumpWidget(carrinho(desconto: 15000, aoMudar: (_) {}));

    expect(find.text('Maior que o subtotal'), findsOneWidget);
    expect(
      find.text('R\$ 0.0'),
      findsOneWidget,
      reason: 'o total nunca fica negativo',
    );
  });

  testWidgets('quem não pode dar desconto não vê o campo', (tester) async {
    await tester.pumpWidget(carrinho());

    expect(find.byKey(const Key('order-discount')), findsNothing);
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
