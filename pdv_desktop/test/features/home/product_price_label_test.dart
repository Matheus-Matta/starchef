import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_price_label.dart';

/// O riscado não é enfeite: sem ele, um produto que amanhece a R$ 15 em vez de
/// R$ 20 parece erro de cadastro, e o operador liga para o escritório antes de
/// vender — na frente do cliente.
void main() {
  String dinheiro(dynamic valor) {
    final numero = valor is num ? valor.toDouble() : double.tryParse('$valor') ?? 0;
    return 'R\$ ${numero.toStringAsFixed(2).replaceAll('.', ',')}';
  }

  Future<void> montar(WidgetTester tester, Map<String, dynamic> produto) =>
      tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ProductPriceLabel(product: produto, money: dinheiro),
          ),
        ),
      );

  testWidgets('sem promoção mostra só o preço, sem riscado', (tester) async {
    await montar(tester, {'current_price': '20.00', 'sale_price': '20.00'});

    expect(find.text('R\$ 20,00'), findsOneWidget);
    expect(find.byType(Column), findsNothing);
  });

  testWidgets('com promoção mostra o "de" riscado acima do "por"', (
    tester,
  ) async {
    await montar(tester, {
      'current_price': '15.00',
      'sale_price': '20.00',
      'compare_at_price': '30.00',
    });

    // O "de" é 30 — MAIOR que o preço cadastrado de 20. É assim que encarte se
    // escreve, e é por isso que o número vem do servidor em vez de ser deduzido
    // aqui comparando `sale_price` com `current_price`.
    expect(find.text('R\$ 30,00'), findsOneWidget);
    expect(find.text('R\$ 15,00'), findsOneWidget);

    final riscado = tester.widget<Text>(find.text('R\$ 30,00'));
    expect(riscado.style?.decoration, TextDecoration.lineThrough);
  });

  testWidgets('não risca quando o "de" não é maior que o cobrado', (
    tester,
  ) async {
    // Um riscado igual ao cobrado é propaganda enganosa, não desconto.
    await montar(tester, {'current_price': '20.00', 'compare_at_price': '20.00'});

    expect(find.text('R\$ 20,00'), findsOneWidget);
    expect(find.byType(Text), findsOneWidget);
  });

  testWidgets('o sufixo do pesável fica fora do riscado', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProductPriceLabel(
            product: const {'current_price': '49.90', 'compare_at_price': '59.90'},
            money: dinheiro,
            suffix: ' / kg',
          ),
        ),
      ),
    );

    expect(find.text('R\$ 49,90 / kg'), findsOneWidget);
    // O "de" já é um número; repetir "/ kg" nele só encompridaria a linha.
    expect(find.text('R\$ 59,90'), findsOneWidget);
  });
}
