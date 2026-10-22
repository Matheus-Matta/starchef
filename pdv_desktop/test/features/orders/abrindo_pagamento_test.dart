import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/order_cart_panel.dart';

/// "Ir para pagamento" enquanto a tela de pagamento abre.
///
/// Com comanda o servidor confere a conta antes, e nada na tela dizia que ele
/// estava trabalhando: o caixa clicava de novo, ou achava que travou. Agora o
/// botão diz "Abrindo pagamento..." e não aceita o segundo clique — o mesmo
/// padrão do "Concluir pedido" ("Calculando total...").
void main() {
  Future<int> montar(WidgetTester tester, {required bool abrindo}) async {
    var cliques = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: ShadTheme(
          data: AppTheme.shadLight(),
          child: Scaffold(
            body: SizedBox(
              width: 420,
              height: 800,
              child: OrderCartPanel(
                order: null,
                table: null,
                customer: null,
                items: const [
                  {
                    'id': 'i1',
                    'product_name': 'Prato feito',
                    'quantity': 1,
                    'unit_price': '25.00',
                    'total_price': '25.00',
                    'status': 'pending',
                  },
                ],
                money: (valor) => '$valor',
                onVoidItem: (_) {},
                onFinish: () => cliques++,
                onSendToKitchen: () {},
                onPrint: () {},
                printing: false,
                abrindoPagamento: abrindo,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.byType(FilledButton).last);
    await tester.pump();
    return cliques;
  }

  testWidgets('abrindo, o botão avisa e não aceita outro clique', (
    tester,
  ) async {
    final cliques = await montar(tester, abrindo: true);

    expect(find.text('Abrindo pagamento...'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(cliques, 0);
  });

  testWidgets('parado, o botão é o de sempre', (tester) async {
    final cliques = await montar(tester, abrindo: false);

    expect(find.text('Ir para pagamento'), findsOneWidget);
    expect(cliques, 1);
  });
}
