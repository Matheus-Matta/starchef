import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/payment_keypad.dart';

/// O teclado divide a altura que sobra em vez de ter proporção fixa.
///
/// Com taxa, CPF/CNPJ e desconto abaixo dele, a grade antiga era cortada nas
/// telas menores: as últimas teclas (C, 0, apagar) sumiam.
void main() {
  testWidgets('cabe numa altura pequena e as teclas respondem', (tester) async {
    final teclas = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 300,
              height: 160,
              child: PaymentKeypad(onKey: teclas.add),
            ),
          ),
        ),
      ),
    );

    for (final tecla in ['7', '0', 'clear', 'back']) {
      await tester.tap(find.byKey(Key('payment-key-$tecla')));
    }

    expect(teclas, ['7', '0', 'clear', 'back']);
    expect(tester.takeException(), isNull);
  });
}
