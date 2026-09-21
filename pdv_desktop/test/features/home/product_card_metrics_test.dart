import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_card_metrics.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_catalog_panel.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/product_catalog_tile.dart';

String _money(dynamic value) =>
    'R\$ ${(value as num).toStringAsFixed(2).replaceAll('.', ',')}';

void main() {
  final products = <Map<String, dynamic>>[
    {
      'id': 'p1',
      'name': 'Picanha maturada ao molho de vinho com batata rústica',
      'internal_code': '104',
      'category': 'c1',
      'category_name': 'Carnes nobres',
      'current_price': 129.9,
      'pricing_unit': 'kg',
    },
    {
      'id': 'p2',
      'name': 'Água',
      'category': 'c1',
      'category_name': 'Bebidas',
      'current_price': 5,
      'pricing_unit': 'unit',
      'is_available': false,
    },
  ];

  Widget catalog({ValueChanged<Map<String, dynamic>>? onPressed}) =>
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: ProductCatalogPanel(
            products: products,
            allProducts: products,
            categories: const [
              {'id': 'c1', 'name': 'Carnes nobres'},
            ],
            selectedCategory: null,
            search: '',
            money: _money,
            onSearchChanged: (_) {},
            onCategoryChanged: (_) {},
            onProductPressed: onPressed ?? (_) {},
          ),
        ),
      );

  testWidgets('catálogo compacto não estoura nas larguras operacionais', (
    tester,
  ) async {
    addTearDown(tester.view.reset);
    for (final width in <double>[420, 640, 900, 1280]) {
      tester.view.physicalSize = Size(width, 700);
      tester.view.devicePixelRatio = 1;
      await tester.pumpWidget(catalog());
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'largura $width');
      expect(
        tester.getSize(find.byType(ProductCatalogTile).first).height,
        ProductCardMetrics.cardHeight,
      );
    }
  });

  testWidgets('peso e indisponibilidade não dependem apenas de cor', (
    tester,
  ) async {
    await tester.pumpWidget(catalog());
    expect(find.text('R\$ 129,90 / kg'), findsOneWidget);
    expect(find.text('Indisponível'), findsOneWidget);
  });

  testWidgets('Enter na busca adiciona o primeiro resultado', (tester) async {
    Map<String, dynamic>? selected;
    await tester.pumpWidget(catalog(onPressed: (item) => selected = item));
    await tester.tap(find.byType(TextField));
    await tester.enterText(find.byType(TextField), 'picanha');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    expect(selected?['id'], 'p1');
  });

  testWidgets('imagem remota preserva proporção na decodificação', (
    tester,
  ) async {
    final withImage = [
      {...products.first, 'image': 'https://example.invalid/picanha.jpg'},
    ];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProductCatalogPanel(
            products: withImage,
            allProducts: withImage,
            categories: const [],
            selectedCategory: null,
            search: '',
            money: _money,
            onSearchChanged: (_) {},
            onCategoryChanged: (_) {},
            onProductPressed: (_) {},
          ),
        ),
      ),
    );
    await tester.pump();
    final image = tester.widget<Image>(find.byType(Image));
    expect((image.image as ResizeImage).width, isNotNull);
    expect((image.image as ResizeImage).height, isNull);
  });
}
