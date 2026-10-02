import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/weighed_product_dialog.dart';

void main() {
  testWidgets('manual weight is the same large field used by the balance', (
    tester,
  ) async {
    WeighedProductSelection? result;
    await _mount(tester, () async {
      result = await showWeighedProductDialog(
        tester.element(find.text('Open')),
        product: _product,
        scales: const [],
        initialScaleId: null,
        readScale: (_) async => const {},
      );
    });

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    final field = find.byKey(const Key('weighed-product-entry'));
    expect(tester.widget<TextField>(field).style?.fontSize, 38);
    await tester.enterText(field, '0,500');
    await tester.pump();
    expect(tester.widget<TextField>(field).controller!.text, '0,500');
    expect(find.text('0,500 kg'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.widgetWithText(FilledButton, 'Adicionar'))
          .onPressed,
      isNotNull,
    );
    await tester.tap(find.text('Adicionar'));
    await tester.pumpAndSettle();

    expect(find.text('Buffet'), findsNothing);
    expect(result?.weightKg, .5);
  });

  testWidgets('amount converts to weight with the final rounded total shown', (
    tester,
  ) async {
    WeighedProductSelection? result;
    await _mount(tester, () async {
      result = await showWeighedProductDialog(
        tester.element(find.text('Open')),
        product: _product,
        scales: const [],
        initialScaleId: null,
        readScale: (_) async => const {},
      );
    });

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Valor'));
    await tester.enterText(
      find.byKey(const Key('weighed-product-entry')),
      '20,00',
    );
    await tester.pump();
    expect(find.text('0,500 kg'), findsOneWidget);
    expect(find.textContaining('20,00'), findsWidgets);
    await tester.tap(find.text('Adicionar'));
    await tester.pumpAndSettle();

    expect(result?.weightKg, .5);
  });

  testWidgets('balance reading populates the same input and stays attached', (
    tester,
  ) async {
    WeighedProductSelection? result;
    await _mount(tester, () async {
      result = await showWeighedProductDialog(
        tester.element(find.text('Open')),
        product: _product,
        scales: const [
          {'id': 'scale-1', 'name': 'Balança do balcão'},
        ],
        initialScaleId: 'scale-1',
        readScale: (_) async => {
          'id': 'reading-1',
          'net_weight_kg': '0.500',
          'is_stable': true,
        },
      );
    });

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ler da balança'));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('weighed-product-entry')))
          .controller!
          .text,
      '0.500',
    );
    await tester.tap(find.text('Adicionar'));
    await tester.pumpAndSettle();

    expect(result?.scaleReading?['id'], 'reading-1');
  });
}

const _product = {
  'id': 'product-kg',
  'name': 'Buffet',
  'current_price': '40.00',
};

Future<void> _mount(WidgetTester tester, Future<void> Function() open) async {
  tester.view.physicalSize = const Size(720, 640);
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.dark(),
      builder: (context, child) =>
          ShadTheme(data: AppTheme.shadDark(), child: child!),
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: FilledButton(
              onPressed: () => unawaited(open()),
              child: const Text('Open'),
            ),
          ),
        ),
      ),
    ),
  );
}
