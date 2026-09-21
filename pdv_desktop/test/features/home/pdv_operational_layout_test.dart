import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/printer.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_navigation_rail.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_navigation_shell.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_operational_chrome.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_shortcut_bar.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_catalog_panel.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/order_cart_panel.dart';

String _money(dynamic value) =>
    'R\$ ${(value as num? ?? 0).toStringAsFixed(2).replaceAll('.', ',')}';

void main() {
  for (final size in [const Size(1366, 768), const Size(1920, 1080)]) {
    testWidgets('venda permanece operacional em ${size.width.toInt()}x'
        '${size.height.toInt()}', (tester) async {
      addTearDown(tester.view.reset);
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      final printer = ValueNotifier(PrinterAvailability.available);
      addTearDown(printer.dispose);
      final products = List.generate(
        24,
        (index) => <String, dynamic>{
          'id': 'p$index',
          'name': 'Produto ${index + 1}',
          'category': 'c1',
          'category_name': 'Refeições',
          'current_price': 10,
        },
      );
      final items = List.generate(
        30,
        (index) => <String, dynamic>{
          'id': 'i$index',
          'product_name': 'Produto ${index + 1}',
          'quantity': 1,
          'unit_price': 10,
          'total_price': 10,
          'status': 'pending',
        },
      );

      await tester.pumpWidget(
        MaterialApp(
          home: ShadTheme(
            data: AppTheme.shadLight(),
            child: Scaffold(
              body: Row(
                children: [
                  PdvNavigationRail(
                    selected: PdvDestination.sale,
                    onSelected: (_) {},
                    showOrders: true,
                    showFinance: true,
                  ),
                  Expanded(
                    child: Column(
                      children: [
                        PdvOperationalBar(
                          cashName: 'Caixa 01',
                          operatorName: 'Operador Matheus',
                          shiftLabel: 'Turno desde 18:00',
                          cashOpen: true,
                          network: const NetworkStatus(
                            phase: NetworkPhase.online,
                          ),
                          printer: printer,
                          syncPending: false,
                        ),
                        Expanded(
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Row(
                              children: [
                                Expanded(
                                  child: ProductCatalogPanel(
                                    products: products,
                                    allProducts: products,
                                    categories: const [
                                      {'id': 'c1', 'name': 'Refeições'},
                                    ],
                                    selectedCategory: null,
                                    search: '',
                                    money: _money,
                                    onSearchChanged: (_) {},
                                    onCategoryChanged: (_) {},
                                    onProductPressed: (_) {},
                                  ),
                                ),
                                const SizedBox(width: 12),
                                SizedBox(
                                  width: size.width >= 1500 ? 400 : 380,
                                  child: OrderCartPanel(
                                    order: const {
                                      'sequence': 84,
                                      'order_type': 'counter',
                                      'subtotal': 300,
                                      'total': 300,
                                    },
                                    table: null,
                                    customer: null,
                                    items: items,
                                    money: _money,
                                    onVoidItem: (_) {},
                                    onFinish: () {},
                                    onSendToKitchen: () {},
                                    onPrint: () {},
                                    printing: false,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const PdvShortcutBar(message: 'Operação normal'),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Total'), findsOneWidget);
      expect(find.text('Ir para pagamento'), findsOneWidget);
      expect(find.text('F4'), findsAtLeastNWidgets(1));
      expect(find.text('Impressora pronta'), findsOneWidget);
    });
  }

  testWidgets('offline e falha temporária têm texto além da cor', (
    tester,
  ) async {
    addTearDown(tester.view.reset);
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    final printer = ValueNotifier(PrinterAvailability.disconnected);
    addTearDown(printer.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Align(
          alignment: Alignment.topCenter,
          child: PdvOperationalBar(
            cashName: 'Caixa 01',
            operatorName: 'Operador',
            shiftLabel: 'Turno desde 18:00',
            cashOpen: true,
            network: const NetworkStatus(phase: NetworkPhase.offline),
            printer: printer,
            syncPending: true,
          ),
        ),
      ),
    );

    expect(find.text('Sem servidor'), findsOneWidget);
    expect(find.text('Sincronização pendente'), findsOneWidget);
    expect(find.text('Tentando impressora'), findsOneWidget);
  });
}
