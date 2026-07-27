import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/home/presentation/pdv_navigation_shell.dart';
import 'package:starchef_pdv/features/home/presentation/product_catalog_panel.dart';
import 'package:starchef_pdv/features/orders/presentation/order_cart_panel.dart';

void main() {
  group('PdvSidebar', () {
    testWidgets('expõe destinos e encaminha ações', (tester) async {
      PdvDestination? selected;
      var toggles = 0;
      var logouts = 0;

      await _pumpAtSize(
        tester,
        size: const Size(800, 640),
        child: PdvSidebar(
          expanded: true,
          selected: PdvDestination.menu,
          onToggle: () => toggles++,
          onSelected: (destination) => selected = destination,
          userName: 'Ana Souza',
          restaurantName: 'StarChef Centro',
          onLogout: () => logouts++,
        ),
      );

      expect(find.text('STARCHEF'), findsOneWidget);
      expect(find.text('Menu'), findsOneWidget);
      expect(find.text('Mesas'), findsOneWidget);
      expect(find.text('Balança rápida'), findsOneWidget);
      expect(find.text('AS'), findsOneWidget);
      expect(find.text('Ana Souza'), findsOneWidget);

      await tester.tap(find.text('Delivery'));
      await tester.tap(find.byTooltip('Recolher menu'));
      await tester.tap(find.text('Sair'));

      expect(selected, PdvDestination.delivery);
      expect(toggles, 1);
      expect(logouts, 1);
      expect(tester.takeException(), isNull);
    });

    testWidgets('rail compacto respeita permissões sem overflow', (
      tester,
    ) async {
      PdvDestination? selected;

      await _pumpAtSize(
        tester,
        size: const Size(180, 520),
        child: PdvSidebar(
          expanded: false,
          selected: PdvDestination.tables,
          onToggle: () {},
          onSelected: (destination) => selected = destination,
          userName: 'Operador',
          restaurantName: 'Unidade',
          onLogout: () {},
          showOrders: false,
          showScale: false,
          showSettings: false,
        ),
      );

      expect(find.text('Pedidos'), findsNothing);
      expect(find.byIcon(Icons.scale_outlined), findsNothing);
      expect(find.byIcon(Icons.settings_outlined), findsNothing);
      expect(find.byTooltip('Expandir menu'), findsOneWidget);

      await tester.tap(find.byIcon(Icons.delivery_dining_outlined));

      expect(selected, PdvDestination.delivery);
      expect(tester.takeException(), isNull);
    });
  });

  group('ProductCatalogPanel', () {
    final products = <Map<String, dynamic>>[
      {
        'id': 'product-1',
        'name': 'Suco de laranja',
        'category': 'category-1',
        'category_name': 'Bebidas',
        'current_price': 12.5,
        'sale_price': 12.5,
        'pricing_unit': 'unit',
      },
      {
        'id': 'product-2',
        'name': 'Hambúrguer artesanal',
        'category': 'category-2',
        'category_name': 'Lanches',
        'current_price': 28,
        'sale_price': 28,
        'pricing_unit': 'unit',
      },
    ];

    testWidgets('filtra categorias e encaminha busca e produto', (
      tester,
    ) async {
      String? search;
      String? category;
      Map<String, dynamic>? pressedProduct;

      await _pumpAtSize(
        tester,
        size: const Size(640, 680),
        child: ProductCatalogPanel(
          products: products,
          allProducts: products,
          categories: const [
            {'id': 'category-1', 'name': 'Bebidas'},
            {'id': 'category-2', 'name': 'Lanches'},
          ],
          selectedCategory: null,
          search: '',
          money: _money,
          imageUrlFor: (_) => null,
          onSearchChanged: (value) => search = value,
          onCategoryChanged: (value) => category = value,
          onProductPressed: (value) => pressedProduct = value,
        ),
      );

      expect(find.text('2 itens'), findsAtLeastNWidgets(1));
      expect(find.text('Suco de laranja'), findsOneWidget);
      expect(find.text('Hambúrguer artesanal'), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'suco');
      await tester.tap(find.text('Bebidas').first);
      await tester.tap(find.text('Suco de laranja'));

      expect(search, 'suco');
      expect(category, 'category-1');
      expect(pressedProduct?['id'], 'product-1');
      expect(tester.takeException(), isNull);
    });

    testWidgets('mostra estado vazio em largura compacta sem overflow', (
      tester,
    ) async {
      await _pumpAtSize(
        tester,
        size: const Size(360, 520),
        child: ProductCatalogPanel(
          products: const [],
          allProducts: const [],
          categories: const [],
          selectedCategory: null,
          search: 'inexistente',
          money: _money,
          imageUrlFor: (_) => null,
          onSearchChanged: (_) {},
          onCategoryChanged: (_) {},
          onProductPressed: (_) {},
        ),
      );

      expect(find.text('0 itens'), findsAtLeastNWidgets(1));
      expect(find.text('Nenhum produto encontrado'), findsOneWidget);
      expect(
        find.text('Tente buscar por outro nome, código ou categoria.'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    });
  });

  group('OrderCartPanel', () {
    testWidgets('desabilita ações e orienta quando o pedido está vazio', (
      tester,
    ) async {
      await _pumpAtSize(
        tester,
        size: const Size(320, 640),
        child: OrderCartPanel(
          order: null,
          table: null,
          customer: null,
          items: const [],
          products: const [],
          money: _money,
          imageUrlFor: (_) => null,
          onVoidItem: (_) {},
          onFinish: () {},
          onPrint: () {},
          printing: false,
        ),
      );

      expect(find.text('Novo pedido'), findsOneWidget);
      expect(find.text('O pedido está vazio'), findsOneWidget);
      expect(
        find.text('Toque em um produto do cardápio para começar.'),
        findsOneWidget,
      );
      expect(
        tester
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, 'Revisar pedido'),
            )
            .onPressed,
        isNull,
      );
      expect(
        tester
            .widget<OutlinedButton>(
              find.widgetWithText(OutlinedButton, 'Imprimir nota do cliente'),
            )
            .onPressed,
        isNull,
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('exibe totais e encaminha remoção, revisão e impressão', (
      tester,
    ) async {
      Map<String, dynamic>? voidedItem;
      var finishes = 0;
      var prints = 0;
      final item = <String, dynamic>{
        'id': 'item-1',
        'product': 'product-1',
        'product_name': 'Prato executivo',
        'quantity': 2,
        'unit_price': 10,
        'total_price': 20,
        'customer_note': 'Sem cebola',
        'status': 'pending',
      };

      await _pumpAtSize(
        tester,
        size: const Size(380, 700),
        child: OrderCartPanel(
          order: const {
            'sequence': 42,
            'order_type': 'table',
            'subtotal': 20,
            'service_fee': 2,
            'discount': 1,
            'total': 21,
            '_offline_pending': true,
          },
          table: const {'number': 7},
          customer: null,
          items: [item],
          products: const [
            {'id': 'product-1', 'name': 'Prato executivo'},
          ],
          money: _money,
          imageUrlFor: (_) => null,
          onVoidItem: (value) => voidedItem = value,
          onFinish: () => finishes++,
          onPrint: () => prints++,
          printing: false,
        ),
      );

      expect(find.text('Pedido #42'), findsOneWidget);
      expect(find.text('Mesa 7 · Salão'), findsOneWidget);
      expect(find.text('LOCAL'), findsOneWidget);
      expect(find.text('Prato executivo'), findsOneWidget);
      expect(find.text('Sem cebola'), findsOneWidget);
      expect(find.text('Taxa de serviço'), findsOneWidget);
      expect(find.text('Desconto'), findsOneWidget);
      expect(find.text('R\$ 21,00'), findsOneWidget);

      await tester.tap(find.byTooltip('Remover item'));
      await tester.tap(find.widgetWithText(FilledButton, 'Revisar pedido'));
      await tester.tap(
        find.widgetWithText(OutlinedButton, 'Imprimir nota do cliente'),
      );

      expect(voidedItem?['id'], 'item-1');
      expect(finishes, 1);
      expect(prints, 1);
      expect(tester.takeException(), isNull);
    });
  });
}

Future<void> _pumpAtSize(
  WidgetTester tester, {
  required Size size,
  required Widget child,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });

  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: const Color(0xFFF57C00),
      ),
      home: Scaffold(body: child),
    ),
  );
  await tester.pump();
}

String _money(dynamic value) {
  final number = value is num ? value.toDouble() : 0;
  return 'R\$ ${number.toStringAsFixed(2).replaceAll('.', ',')}';
}
