import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/errors/app_error.dart';
import 'package:starchef_pdv_desktop/core/errors/app_error_host.dart';
import 'package:starchef_pdv_desktop/core/errors/error_center.dart';
import 'package:starchef_pdv_desktop/core/errors/notification_bell.dart';
import 'package:starchef_pdv_desktop/core/widgets/responsive_scale.dart';

void main() {
  Widget app(ErrorCenter center) => MaterialApp(
    builder: (context, child) => ResponsiveScale(
      child: AppErrorHost(center: center, child: child!),
    ),
    home: Scaffold(
      appBar: AppBar(
        title: const Text('Venda'),
        actions: const [NotificationBell()],
      ),
      body: const Center(child: Text('Catálogo')),
    ),
  );

  testWidgets('sino vazio abre e fecha sem exceções', (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final center = ErrorCenter();
    addTearDown(center.dispose);

    await tester.pumpWidget(app(center));
    await tester.tap(find.byTooltip('Notificações'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Nada por aqui ainda.'), findsOneWidget);
    await tester.tap(find.byTooltip('Notificações'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('histórico cheio abre e atualiza sem travar', (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final center = ErrorCenter();
    addTearDown(center.dispose);
    for (var i = 0; i < 20; i++) {
      center.report(
        AppError(
          title: 'Aviso $i',
          message: 'Mensagem operacional $i',
          severity: AppErrorSeverity.info,
        ),
      );
    }
    await tester.pumpWidget(app(center));

    await tester.tap(find.byTooltip('20 notificações novas'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Aviso 19'), findsOneWidget);
    expect(center.unreadCount, 0);

    center.report(
      AppError(
        title: 'Novo aviso',
        message: 'Conexão restabelecida',
        severity: AppErrorSeverity.success,
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Novo aviso'), findsOneWidget);

    await tester.tap(find.text('Limpar'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(center.history, isEmpty);
  });
}
