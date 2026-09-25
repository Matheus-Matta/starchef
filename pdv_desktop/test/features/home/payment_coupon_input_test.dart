import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/payment_coupon_input.dart';

/// O cliente lembra do cupom quando o caixa fala o total — é o caso normal, não
/// a exceção. Estes testes fixam o que a mão do operador encontra nesse momento.
void main() {
  late TextEditingController controller;

  setUp(() => controller = TextEditingController());
  tearDown(() => controller.dispose());

  Future<void> montar(
    WidgetTester tester, {
    String applied = '',
    bool busy = false,
    String error = '',
    ValueChanged<String>? onSubmit,
    VoidCallback? onRemove,
  }) => tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PaymentCouponInput(
          controller: controller,
          applied: applied,
          busy: busy,
          error: error,
          onSubmit: onSubmit ?? (_) {},
          onRemove: onRemove ?? () {},
        ),
      ),
    ),
  );

  testWidgets('sem cupom aplicado o botão é Aplicar, e ele fica inerte vazio', (
    tester,
  ) async {
    var chamou = false;
    await montar(tester, onSubmit: (_) => chamou = true);

    expect(find.text('Aplicar'), findsOneWidget);
    expect(find.text('Retirar'), findsNothing);

    // Campo vazio não vale uma ida ao servidor: a recusa seria "informe o
    // código", que o operador já sabe olhando a tela.
    await tester.tap(find.byKey(const Key('payment-coupon-apply')));
    await tester.pump();
    expect(chamou, isFalse);
  });

  testWidgets('manda o código digitado, sem espaços nas pontas', (tester) async {
    String? enviado;
    await montar(tester, onSubmit: (codigo) => enviado = codigo);

    await tester.enterText(find.byType(TextField), '  natal10  ');
    await tester.pump();
    await tester.tap(find.byKey(const Key('payment-coupon-apply')));

    expect(enviado, 'natal10');
  });

  testWidgets('com cupom aplicado oferece Trocar E Retirar', (tester) async {
    // São gestos diferentes com a mesma urgência: o cliente trouxe outro cupom,
    // ou desistiu deste. Um botão só obrigaria o operador a apagar o campo para
    // descobrir que aquilo também removia.
    await montar(tester, applied: 'NATAL10');

    expect(find.text('Trocar'), findsOneWidget);
    expect(find.text('Retirar'), findsOneWidget);
    expect(find.text('Aplicar'), findsNothing);
  });

  testWidgets('Retirar avisa quem sabe remover', (tester) async {
    var removeu = false;
    await montar(tester, applied: 'NATAL10', onRemove: () => removeu = true);

    await tester.tap(find.byKey(const Key('payment-coupon-remove')));
    expect(removeu, isTrue);
  });

  testWidgets('a recusa do servidor aparece inteira, em até três linhas', (
    tester,
  ) async {
    const motivo =
        'Este cupom vale a partir de R\$ 100,00 em produtos '
        '(sem taxa de serviço e sem entrega).';
    await montar(tester, error: motivo);

    expect(find.text(motivo), findsOneWidget);
    final campo = tester.widget<TextField>(find.byType(TextField));
    // Cortar em uma linha deixaria "Este cupom vale a partir de…", que não
    // resolve nada para quem está atendendo.
    expect(campo.decoration?.errorMaxLines, 3);
  });

  testWidgets('enquanto o servidor responde, o campo trava e some o botão', (
    tester,
  ) async {
    await montar(tester, busy: true, applied: 'NATAL10');

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Trocar'), findsNothing);
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);
  });
}
