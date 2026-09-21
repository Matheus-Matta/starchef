import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/printer.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_cash_center_dialog.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_navigation_rail.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_navigation_shell.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_operational_chrome.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_card_metrics.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_catalog_tile.dart';

void main() {
  testWidgets('balança rápida tem destino próprio na barra lateral', (
    tester,
  ) async {
    PdvDestination? selected;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PdvNavigationRail(
            selected: PdvDestination.sale,
            onSelected: (value) => selected = value,
            showOrders: true,
            showFinance: true,
          ),
        ),
      ),
    );
    await tester.tap(find.text('Balança'));
    expect(selected, PdvDestination.scale);
    expect(tester.takeException(), isNull);
  });

  testWidgets('caixa oferece ver saldo sem esconder a ação', (tester) async {
    String? action;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        builder: (context, child) =>
            ShadTheme(data: AppTheme.shadLight(), child: child!),
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () async => action = await PdvCashCenterDialog.show(
                context,
                cashSession: {'id': 'caixa-1', 'name': 'Caixa PDV 1'},
                balanceLabel: '••••••',
                balanceVisible: false,
              ),
              child: const Text('Caixa'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Caixa'));
    await tester.pumpAndSettle();
    expect(find.text('Ver saldo'), findsOneWidget);
    await tester.tap(find.text('Ver saldo'));
    await tester.pumpAndSettle();
    expect(action, 'toggle_balance');
    expect(tester.takeException(), isNull);
  });

  testWidgets('estado fica ao lado do nome do caixa no cabeçalho', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final printer = ValueNotifier(PrinterAvailability.available);
    addTearDown(printer.dispose);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: PdvOperationalBar(
            cashName: 'CAIXA PDV 1',
            operatorName: 'Caixa 1',
            shiftLabel: 'Turno desde 08:00',
            cashOpen: true,
            network: const NetworkStatus(phase: NetworkPhase.online),
            printer: printer,
            syncPending: false,
          ),
        ),
      ),
    );
    expect(find.text('CAIXA PDV 1'), findsOneWidget);
    expect(find.text('Aberto'), findsOneWidget);
    expect(find.text('Operador: Caixa 1'), findsOneWidget);
    expect(find.text('Caixa aberto'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  test('tema claro usa superfícies quentes e contraste alto', () {
    final scheme = AppTheme.light().colorScheme;
    expect(scheme.surface, isNot(Colors.white));
    expect(scheme.surface, isNot(scheme.surfaceContainerLowest));
    final lighter = scheme.surface.computeLuminance();
    final darker = scheme.onSurface.computeLuminance();
    expect((lighter + 0.05) / (darker + 0.05), greaterThan(7));
  });

  testWidgets('produto não começa selecionado e foto é quadrada', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 380,
              height: ProductCardMetrics.cardHeight,
              child: ProductCatalogTile(
                product: const {
                  'id': 'p1',
                  'name': 'Água 350 ml',
                  'current_price': 4.0,
                },
                money: (_) => 'R\$ 4,00',
                onPressed: () {},
              ),
            ),
          ),
        ),
      ),
    );
    final material = tester.widget<Material>(
      find
          .descendant(
            of: find.byType(ProductCatalogTile),
            matching: find.byType(Material),
          )
          .first,
    );
    final shape = material.shape! as RoundedRectangleBorder;
    expect(shape.side.color, AppTheme.light().colorScheme.outlineVariant);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is SizedBox &&
            widget.width == ProductCardMetrics.cardHeight - 2 &&
            widget.height == ProductCardMetrics.cardHeight - 2,
      ),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });
}
