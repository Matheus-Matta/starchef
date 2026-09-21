import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/orders_date_range_menu.dart';

void main() {
  testWidgets('personalizado abre calendário no próprio menu', (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    DateTimeRange? selected;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: 220,
              height: 48,
              child: Align(
                alignment: Alignment.centerLeft,
                child: OrdersDateRangeMenu(
                  label: 'Período',
                  range: null,
                  onChanged: (value) => selected = value,
                ),
              ),
            ),
          ),
        ),
      ),
    );

    final buttonSize = tester.getSize(find.byType(OutlinedButton));
    expect(buttonSize.height, AppTheme.controlHeight);
    expect(buttonSize.width, lessThan(220));

    await tester.tap(find.text('Período'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Personalizado…'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.byType(CalendarDatePicker), findsOneWidget);
    expect(find.byType(Dialog), findsNothing);
    expect(selected, isNull);

    await tester.tap(find.text('Aplicar'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(selected, isNull, reason: 'sem data o botão deve ficar desativado');

    await tester.tap(find.text('${DateTime.now().day}').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Aplicar'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(selected?.start, selected?.end);
    expect(selected, isNotNull);
  });
}
