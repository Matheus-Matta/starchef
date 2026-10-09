import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/command_void_dialog.dart';

/// Cancelar item da comanda: o motivo é um toque, não uma digitação.
void main() {
  Future<String?> abrir(
    WidgetTester tester,
    Future<void> Function() gesto,
  ) async {
    String? motivo = 'nada';
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) =>
            ShadTheme(data: AppTheme.shadLight(), child: child!),
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async => motivo = await showCommandVoidDialog(
              context,
              item: const {'product_name': 'Coca', 'status': 'pending'},
            ),
            child: const Text('abrir'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();
    await gesto();
    await tester.tap(find.text('Remover item').last);
    await tester.pumpAndSettle();
    return motivo;
  }

  testWidgets('um toque no motivo e confirmar', (tester) async {
    final motivo = await abrir(tester, () async {
      await tester.tap(find.text('Cliente desistiu'));
      await tester.pump();
    });
    expect(motivo, 'Cliente desistiu');
  });

  testWidgets('"Outro" continua aceitando o motivo digitado', (tester) async {
    final motivo = await abrir(tester, () async {
      await tester.tap(find.text('Outro'));
      await tester.pump();
      await tester.enterText(find.byType(TextField), 'Mesa trocou o pedido');
      await tester.pump();
    });
    expect(motivo, 'Mesa trocou o pedido');
  });
}
