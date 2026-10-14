import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_cash_center_dialog.dart';

/// Reimprimir está no centro de caixa com o caixa aberto OU fechado: o
/// relatório de fechamento perdido é justamente de um caixa já fechado.
void main() {
  Future<String?> escolher(
    WidgetTester tester, {
    required Map<String, dynamic>? sessao,
    required String chave,
  }) async {
    String? escolhido;
    await tester.binding.setSurfaceSize(const Size(900, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark(),
        builder: (context, child) =>
            ShadTheme(data: AppTheme.shadDark(), child: child!),
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async => escolhido = await PdvCashCenterDialog.show(
              context,
              cashSession: sessao,
              balanceLabel: r'R$ 10,00',
            ),
            child: const Text('abrir'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(Key(chave)));
    await tester.pumpAndSettle();
    return escolhido;
  }

  testWidgets('caixa fechado reimprime o ultimo fechamento', (tester) async {
    expect(
      await escolher(tester, sessao: null, chave: 'cash-reprint-closing'),
      'reprint_closing',
    );
  });

  testWidgets('caixa aberto reimprime a abertura', (tester) async {
    expect(
      await escolher(
        tester,
        sessao: {'id': 's1', 'station': 'Caixa 01'},
        chave: 'cash-reprint-opening',
      ),
      'reprint_opening',
    );
  });
}
