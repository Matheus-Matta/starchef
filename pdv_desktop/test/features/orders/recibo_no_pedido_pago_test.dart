import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/order_cart_panel.dart';

/// O pedido pago ainda imprime o recibo (não fiscal).
///
/// Produção, 20/11/2026: aberto um pedido já pago, a tela virava "somente
/// consulta" e o botão "Recibo" sumia junto com os de edição — o cliente
/// pedia a segunda via e o caixa não tinha como dar.
///
/// O recibo NÃO substitui a nota: os dois ficam juntos. O não fiscal é a
/// segunda via, e o plano B quando o DANFE não sai.
void main() {
  Future<int> montar(
    WidgetTester tester, {
    required String status,
    Map<String, dynamic>? fiscal,
  }) async {
    var impressoes = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: ShadTheme(
          data: AppTheme.shadLight(),
          child: Scaffold(
            body: SizedBox(
              width: 420,
              height: 800,
              child: OrderCartPanel(
                order: {
                  'id': 'p1',
                  'status': status,
                  'payment_status': status == 'paid' ? 'paid' : 'pending',
                  'total': '25.00',
                  'fiscal': ?fiscal,
                },
                table: null,
                customer: null,
                items: const [
                  {
                    'id': 'i1',
                    'product_name': 'Prato feito',
                    'quantity': 1,
                    'unit_price': '25.00',
                    'total_price': '25.00',
                    'status': 'delivered',
                  },
                ],
                money: (valor) => '$valor',
                onVoidItem: (_) {},
                onFinish: () {},
                onSendToKitchen: () {},
                onPrint: () => impressoes++,
                printing: false,
                abrindoPagamento: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Recibo'));
    await tester.pump();
    return impressoes;
  }

  testWidgets('pedido pago: somente consulta, mas o recibo imprime', (
    tester,
  ) async {
    final impressoes = await montar(tester, status: 'paid');

    expect(find.text('Somente consulta'), findsOneWidget);
    expect(find.text('Ir para pagamento'), findsNothing);
    expect(find.text('Emitir NFC-e'), findsOneWidget);
    expect(impressoes, 1);
  });

  testWidgets('nota autorizada: Imprimir DANFE e Recibo, os dois juntos', (
    tester,
  ) async {
    final impressoes = await montar(
      tester,
      status: 'paid',
      fiscal: {'printable': true, 'fiscal_state': 'authorized'},
    );

    expect(find.text('Imprimir DANFE'), findsOneWidget);
    expect(impressoes, 1);
  });

  testWidgets('nota com erro: Reenviar e imprimir e o Recibo como plano B', (
    tester,
  ) async {
    final impressoes = await montar(
      tester,
      status: 'paid',
      fiscal: {'printable': false, 'fiscal_state': 'rejected'},
    );

    expect(find.text('Reenviar e imprimir NFC-e'), findsOneWidget);
    expect(impressoes, 1);
  });

  testWidgets('pedido cancelado reimprime o comprovante pelo mesmo botão', (
    tester,
  ) async {
    expect(await montar(tester, status: 'cancelled'), 1);
  });
}
