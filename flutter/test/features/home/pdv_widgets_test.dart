import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/theme/app_theme.dart';
import 'package:starchef_pdv/core/update/pdv_update_service.dart';
import 'package:starchef_pdv/features/home/presentation/pdv_navigation_shell.dart';
import 'package:starchef_pdv/features/home/presentation/product_catalog_panel.dart';
import 'package:starchef_pdv/features/orders/presentation/order_cart_panel.dart';

void main() {
  group('PdvSidebar', () {
    testWidgets('mostra versão instalada e atualização disponível', (
      tester,
    ) async {
      await _pumpAtSize(
        tester,
        size: const Size(800, 640),
        child: PdvSidebar(
          expanded: true,
          selected: PdvDestination.menu,
          onToggle: () {},
          onSelected: (_) {},
          userName: 'Operador',
          userSubtitle: '@operador',
          onLogout: () {},
          versionStatus: const PdvUpdateStatus(
            phase: PdvUpdatePhase.updateAvailable,
            installed: PdvInstalledVersion(
              version: '1.0.33',
              buildNumber: '31',
            ),
            latestVersion: '1.0.34',
          ),
        ),
      );

      expect(find.text('v1.0.33+31'), findsOneWidget);
      expect(find.text('Nova v1.0.34 disponível'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

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
          userSubtitle: '@ana · Operadora',
          onLogout: () => logouts++,
        ),
      );

      expect(find.text('STARCHEF'), findsOneWidget);
      expect(find.text('Menu'), findsOneWidget);
      expect(find.text('Mesas'), findsOneWidget);
      expect(find.text('Balança rápida'), findsOneWidget);
      expect(find.text('AS'), findsOneWidget);
      expect(find.text('Ana Souza'), findsOneWidget);
      expect(find.text('@ana · Operadora'), findsOneWidget);
      expect(find.text('StarChef Centro'), findsNothing);

      // Delivery deixou de ser um módulo da barra lateral; ele existe apenas
      // como tipo de pedido dentro do fluxo de Pedidos.
      expect(find.text('Delivery'), findsNothing);

      await tester.tap(find.text('Financeiro'));
      await tester.tap(find.byTooltip('Recolher menu'));
      await tester.tap(find.text('Sair'));

      expect(selected, PdvDestination.finance);
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
          userSubtitle: '@operador',
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

      expect(find.byIcon(Icons.delivery_dining_outlined), findsNothing);

      await tester.tap(find.byIcon(Icons.table_restaurant_outlined));

      expect(selected, PdvDestination.tables);
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
          onSearchChanged: (value) => search = value,
          onCategoryChanged: (value) => category = value,
          onProductPressed: (value) => pressedProduct = value,
        ),
      );

      expect(find.text('2 itens'), findsAtLeastNWidgets(1));
      expect(find.text('Suco de laranja'), findsOneWidget);
      expect(find.text('Hambúrguer artesanal'), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'suco');
      // A faixa de categorias permanece visível para seleção rápida no PDV.
      await tester.tap(find.text('Bebidas · 1'));
      await tester.pumpAndSettle();
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

    testWidgets('card do produto não estoura com nome de 2 linhas + pesado + '
        'promocional', (tester) async {
      // Pior caso empilhado: nome longo o bastante para 2 linhas, unidade
      // "/ kg" e preço promocional riscado — os três elementos que competem
      // por altura dentro do card ao mesmo tempo.
      final heavy = <Map<String, dynamic>>[
        {
          'id': 'product-1',
          'name': 'Picanha Angus Premium Fatiada Especial',
          'category': 'category-1',
          'category_name': 'Carnes nobres',
          'current_price': 89.9,
          'sale_price': 109.9,
          'promotional_price': 89.9,
          'pricing_unit': 'kg',
          'is_weighed': true,
        },
      ];

      await _pumpAtSize(
        tester,
        size: const Size(1280, 800),
        child: ProductCatalogPanel(
          products: heavy,
          allProducts: heavy,
          categories: const [
            {'id': 'category-1', 'name': 'Carnes nobres'},
          ],
          selectedCategory: null,
          search: '',
          money: _money,
          onSearchChanged: (_) {},
          onCategoryChanged: (_) {},
          onProductPressed: (_) {},
        ),
      );

      expect(find.textContaining('Picanha'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('mostra o código do produto com # ao lado do título', (
      tester,
    ) async {
      final coded = <Map<String, dynamic>>[
        {
          'id': 'product-1',
          'name': 'Suco de laranja',
          'internal_code': '104',
          'category': 'category-1',
          'category_name': 'Bebidas',
          'current_price': 12.5,
          'sale_price': 12.5,
          'pricing_unit': 'unit',
        },
      ];

      await _pumpAtSize(
        tester,
        size: const Size(640, 680),
        child: ProductCatalogPanel(
          products: coded,
          allProducts: coded,
          categories: const [
            {'id': 'category-1', 'name': 'Bebidas'},
          ],
          selectedCategory: null,
          search: '',
          money: _money,
          onSearchChanged: (_) {},
          onCategoryChanged: (_) {},
          onProductPressed: (_) {},
        ),
      );

      expect(find.textContaining('#104'), findsOneWidget);
      expect(find.textContaining('Suco de laranja'), findsOneWidget);
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
          money: _money,
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
              find.widgetWithText(OutlinedButton, 'Imprimir recibo de venda'),
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
      var cancellations = 0;
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
          money: _money,
          onVoidItem: (value) => voidedItem = value,
          onFinish: () => finishes++,
          onPrint: () => prints++,
          onCancel: () => cancellations++,
          printing: false,
        ),
      );

      expect(find.text('Pedido #42'), findsOneWidget);
      expect(find.text('Mesa 7 · Histórico'), findsOneWidget);
      expect(find.text('LOCAL'), findsOneWidget);
      expect(find.text('Prato executivo'), findsOneWidget);
      expect(find.text('Sem cebola'), findsOneWidget);
      expect(find.text('Taxa de serviço'), findsOneWidget);
      expect(find.text('Desconto'), findsOneWidget);
      expect(find.text('R\$ 21,00'), findsOneWidget);

      await tester.tap(find.byTooltip('Cancelar item'));
      await tester.tap(find.widgetWithText(FilledButton, 'Revisar pedido'));
      await tester.tap(
        find.widgetWithText(OutlinedButton, 'Imprimir recibo de venda'),
      );
      await tester.tap(find.byTooltip('Mais ações do pedido'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancelar pedido'));
      await tester.pumpAndSettle();

      expect(voidedItem?['id'], 'item-1');
      expect(finishes, 1);
      expect(prints, 1);
      expect(cancellations, 1);
      expect(tester.takeException(), isNull);
    });

    testWidgets('identifica o pedido pela comanda quando não há mesa', (
      tester,
    ) async {
      await _pumpAtSize(
        tester,
        size: const Size(380, 700),
        child: OrderCartPanel(
          order: const {'sequence': 51, 'order_type': 'command', 'total': 0},
          table: null,
          command: const {'number': 12, 'customer_name': 'Ana'},
          customer: null,
          items: const [],
          money: _money,
          onVoidItem: (_) {},
          onFinish: () {},
          onPrint: () {},
          printing: false,
        ),
      );

      // Sem isso o cabeçalho cairia no rótulo genérico do tipo e o operador
      // não saberia qual cartão está na mão.
      expect(find.text('Comanda 12 · Ana'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('comanda sem cliente ainda diz que é self-service', (
      tester,
    ) async {
      await _pumpAtSize(
        tester,
        size: const Size(380, 700),
        child: OrderCartPanel(
          order: const {'sequence': 52, 'order_type': 'command', 'total': 0},
          table: null,
          command: const {'number': 3, 'customer_name': ''},
          customer: null,
          items: const [],
          money: _money,
          onVoidItem: (_) {},
          onFinish: () {},
          onPrint: () {},
          printing: false,
        ),
      );

      expect(find.text('Comanda 3 · Self-service'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets('PdvConnectionBadge online usa verde escuro com alto contraste', (
    tester,
  ) async {
    await _pumpAtSize(
      tester,
      size: const Size(240, 100),
      child: const PdvConnectionBadge(
        status: NetworkSyncStatus(phase: NetworkSyncPhase.online),
      ),
    );

    final badge = tester.widget<ShadBadge>(find.byType(ShadBadge));
    expect(badge.backgroundColor, const Color(0xFF166534));
    expect(badge.hoverBackgroundColor, const Color(0xFF14532D));
    expect(badge.foregroundColor, Colors.white);
    expect(find.text('Online'), findsOneWidget);
  });

  group('PdvPrincipalBadge', () {
    testWidgets('avisa que o caixa não grava sem o principal', (tester) async {
      var taps = 0;

      await _pumpAtSize(
        tester,
        size: const Size(400, 200),
        child: PdvPrincipalBadge(
          connected: false,
          detail: 'Caixa Principal 192.168.1.10:47832 indisponível.',
          onPressed: () => taps++,
        ),
      );

      // O operador precisa ver isso antes de montar o pedido inteiro, não
      // depois de tentar lançar.
      expect(find.text('Sem o Principal'), findsOneWidget);

      await tester.tap(find.byType(PdvPrincipalBadge));
      expect(taps, 1);
      expect(tester.takeException(), isNull);
    });

    testWidgets('mostra a ligação ativa quando o principal responde', (
      tester,
    ) async {
      await _pumpAtSize(
        tester,
        size: const Size(400, 200),
        child: const PdvPrincipalBadge(
          connected: true,
          detail: 'Conectado ao Caixa Principal 192.168.1.10.',
        ),
      );

      expect(find.text('Principal'), findsOneWidget);
      expect(find.text('Sem o Principal'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('cabe ao lado do indicador de conexão em tela estreita', (
      tester,
    ) async {
      await _pumpAtSize(
        tester,
        size: const Size(360, 120),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            PdvConnectionBadge(
              status: NetworkSyncStatus(phase: NetworkSyncPhase.offline),
            ),
            SizedBox(width: 8),
            PdvPrincipalBadge(connected: false, detail: '', compact: true),
          ],
        ),
      );

      // O cabeçalho do PDV já estourou antes por um widget a mais; em tela
      // estreita o badge fica só com o ícone e o texto vai para o tooltip.
      expect(tester.takeException(), isNull);
      expect(find.text('Sem o Principal'), findsNothing);
      expect(find.byIcon(Icons.lan_outlined), findsOneWidget);
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
      home: ShadTheme(
        data: AppTheme.shadLight(),
        child: Scaffold(body: child),
      ),
    ),
  );
  await tester.pump();
}

String _money(dynamic value) {
  final number = value is num ? value.toDouble() : 0;
  return 'R\$ ${number.toStringAsFixed(2).replaceAll('.', ',')}';
}
