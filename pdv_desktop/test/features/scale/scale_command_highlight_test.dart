import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/scale/presentation/scale_command_highlight.dart';

/// Lida a comanda, a coluna da direita mostra o número e o total GRANDES —
/// é o que o cliente e o operador conferem de longe antes de tirar o prato.
void main() {
  Future<void> montar(WidgetTester tester, Widget child) => tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: SizedBox(width: 360, child: child)),
    ),
  );

  testWidgets('mostra a comanda lida sem os zeros e o total grande', (
    tester,
  ) async {
    await montar(
      tester,
      const ScaleCommandHighlight(
        commandCode: '0017',
        totalLabel: r'R$ 26,96',
        status: 'Finalizando. Não retire a comanda.',
      ),
    );

    final numero = tester.widget<Text>(
      find.byKey(const ValueKey('balanca-comanda-numero')),
    );
    final total = tester.widget<Text>(
      find.byKey(const ValueKey('balanca-comanda-total')),
    );
    expect(numero.data, '17');
    expect(numero.style!.fontSize, greaterThanOrEqualTo(72));
    expect(total.data, r'R$ 26,96');
    expect(total.style!.fontSize, greaterThanOrEqualTo(40));
    expect(find.text('Finalizando. Não retire a comanda.'), findsOneWidget);
  });

  testWidgets('antes de ler a comanda, só o total a lançar, também grande', (
    tester,
  ) async {
    await montar(tester, const ScaleCommandHighlight(totalLabel: r'R$ 26,96'));

    expect(find.byKey(const ValueKey('balanca-comanda-numero')), findsNothing);
    expect(find.text('TOTAL A LANÇAR'), findsOneWidget);
    final total = tester.widget<Text>(
      find.byKey(const ValueKey('balanca-comanda-total')),
    );
    expect(total.style!.fontSize, greaterThanOrEqualTo(40));
  });
}
