import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv/core/theme/app_theme.dart';
import 'package:starchef_pdv/core/widgets/supervisor_close_dialog.dart';

void main() {
  testWidgets('abre pelo contexto do Navigator com MaterialLocalizations', (
    tester,
  ) async {
    final navigatorKey = GlobalKey<NavigatorState>();
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigatorKey,
        theme: AppTheme.dark(),
        builder: (context, child) =>
            ShadTheme(data: AppTheme.shadDark(), child: child!),
        home: const Scaffold(body: SizedBox()),
      ),
    );

    final result = showSupervisorCloseDialog(
      context: navigatorKey.currentContext!,
      title: 'Fechar o PDV',
      description: 'Confirme o fechamento.',
      confirmLabel: 'Fechar',
      verifyPassword: (_) async => true,
    );
    await tester.pumpAndSettle();

    expect(find.text('Fechar o PDV'), findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.tap(find.text('Manter aberto'));
    await tester.pumpAndSettle();
    expect(await result, isFalse);
  });

  testWidgets('confirma após validar a senha do Supervisor', (tester) async {
    final navigatorKey = GlobalKey<NavigatorState>();
    String? receivedPassword;
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigatorKey,
        theme: AppTheme.dark(),
        builder: (context, child) =>
            ShadTheme(data: AppTheme.shadDark(), child: child!),
        home: const Scaffold(body: SizedBox()),
      ),
    );

    final result = showSupervisorCloseDialog(
      context: navigatorKey.currentContext!,
      title: 'Fechar a Balança Rápida',
      description: 'Confirme o fechamento.',
      confirmLabel: 'Fechar balança',
      verifyPassword: (password) async {
        receivedPassword = password;
        return true;
      },
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.enterText(find.byType(TextField), 'senha-segura');
    await tester.tap(find.text('Fechar balança'));
    await tester.pumpAndSettle();

    expect(receivedPassword, 'senha-segura');
    expect(await result, isTrue);
    expect(tester.takeException(), isNull);
  });
}
