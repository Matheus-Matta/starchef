import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/features/orders/presentation/order_dialogs.dart';

/// O garçom cancela um item com um toque no motivo — não digitando no celular
/// com o cliente esperando. "Outro" ainda deixa escrever.
void main() {
  Future<String?> abrir(
    WidgetTester tester,
    Future<void> Function() gesto,
  ) async {
    String? motivo = 'nada';
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async => motivo = await askVoidReason(context, const {
              'product_name': 'Coca',
            }),
            child: const Text('abrir'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();
    await gesto();
    await tester.tap(find.text('Cancelar item'));
    await tester.pumpAndSettle();
    return motivo;
  }

  testWidgets('motivo é um toque', (tester) async {
    final motivo = await abrir(tester, () async {
      await tester.tap(find.text('Cliente desistiu'));
      await tester.pump();
    });
    expect(motivo, 'Cliente desistiu');
  });

  testWidgets('"Outro" deixa escrever', (tester) async {
    final motivo = await abrir(tester, () async {
      await tester.tap(find.text('Outro'));
      await tester.pump();
      await tester.enterText(find.byType(TextField), 'Mesa mudou de ideia');
      await tester.pump();
    });
    expect(motivo, 'Mesa mudou de ideia');
  });

  testWidgets('sem escolher nada não cancela', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () =>
                askVoidReason(context, const {'product_name': 'Coca'}),
            child: const Text('abrir'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancelar item'));
    await tester.pumpAndSettle();
    expect(
      find.text('Cancelar item'),
      findsOneWidget,
    ); // o diálogo continua aberto
  });
}
