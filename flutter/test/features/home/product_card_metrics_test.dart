import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv/core/theme/app_theme.dart';
import 'package:starchef_pdv/features/home/presentation/product_card_metrics.dart';
import 'package:starchef_pdv/features/home/presentation/product_catalog_panel.dart';

String _money(dynamic value) =>
    'R\$ ${(value as num).toStringAsFixed(2).replaceAll('.', ',')}';

void main() {
  group('o card de produto', () {
    // Um nome longo o bastante para ocupar as DUAS linhas do título: é o pior
    // caso, e é ele que decide a altura reservada ao texto.
    final produtos = <Map<String, dynamic>>[
      {
        'id': 'p1',
        'name': 'Picanha maturada ao molho de vinho tinto com batata rústica',
        'internal_code': '104',
        'category': 'c1',
        'category_name': 'Carnes nobres',
        'current_price': 129.9,
        'sale_price': 149.9,
        'promotional_price': 129.9,
        'pricing_unit': 'kg',
        'is_weighed': true,
      },
      {
        'id': 'p2',
        'name': 'Água',
        'category': 'c1',
        'category_name': 'Bebidas',
        'current_price': 5,
        'sale_price': 5,
        'pricing_unit': 'unit',
      },
    ];

    testWidgets('a foto mede 80% da largura em altura, e o texto cabe', (
      tester,
    ) async {
      addTearDown(tester.view.reset);

      // Larguras que mudam o número de colunas — é aí que a largura de cada
      // card muda, e com ela o lado do quadrado.
      for (final largura in <double>[420, 640, 900, 1280]) {
        tester.view.physicalSize = Size(largura, 700);
        tester.view.devicePixelRatio = 1;

        await tester.pumpWidget(
          MaterialApp(
            theme: AppTheme.light(),
            home: ShadTheme(
              data: AppTheme.shadLight(),
              child: Scaffold(
                body: ProductCatalogPanel(
                  products: produtos,
                  allProducts: produtos,
                  categories: const [
                    {'id': 'c1', 'name': 'Carnes nobres'},
                  ],
                  selectedCategory: null,
                  search: '',
                  money: _money,
                  onSearchChanged: (_) {},
                  onCategoryChanged: (_) {},
                  onProductPressed: (_) {},
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(
          tester.takeException(),
          isNull,
          reason: 'o card estourou com o painel em ${largura}px',
        );

        // A proporção tem que valer em QUALQUER largura de painel: é a
        // largura da coluna que muda quando o número de colunas muda, e a
        // altura reservada na grade acompanha por essa mesma conta. Se as
        // duas discordarem, sobra faixa embaixo da foto ou o card estoura.
        final foto = tester.getSize(find.byType(AspectRatio).first);
        expect(
          foto.height,
          closeTo(foto.width * ProductCardMetrics.photoHeightFactor, 0.5),
          reason: 'a foto saiu fora de proporção com o painel em ${largura}px',
        );
      }
    });

    testWidgets('a foto não é decodificada com as duas medidas', (
      tester,
    ) async {
      addTearDown(tester.view.reset);
      tester.view.physicalSize = const Size(900, 700);
      tester.view.devicePixelRatio = 1;

      final comFoto = <Map<String, dynamic>>[
        {
          'id': 'p1',
          'name': 'Picanha',
          'category': 'c1',
          'category_name': 'Carnes nobres',
          'current_price': 129.9,
          'sale_price': 129.9,
          'pricing_unit': 'unit',
          'image': 'https://exemplo.invalido/picanha.jpg',
        },
      ];

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: ShadTheme(
            data: AppTheme.shadLight(),
            child: Scaffold(
              body: ProductCatalogPanel(
                products: comFoto,
                allProducts: comFoto,
                categories: const [
                  {'id': 'c1', 'name': 'Carnes nobres'},
                ],
                selectedCategory: null,
                search: '',
                money: _money,
                onSearchChanged: (_) {},
                onCategoryChanged: (_) {},
                onProductPressed: (_) {},
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      // `cacheWidth` E `cacheHeight` juntos mandam o decodificador entregar o
      // bitmap naquela medida exata, IGNORANDO a proporção do arquivo: a foto
      // chega deformada e o `BoxFit.cover` não tem como desfazer. Numa moldura
      // quadrada isso vira um prato deitado ficando em pé.
      final imagem = tester.widget<Image>(find.byType(Image));
      expect(imagem.width, isNull);
      expect(
        (imagem.image as ResizeImage).height,
        isNull,
        reason: 'fixar as duas medidas deforma a foto',
      );
      expect((imagem.image as ResizeImage).width, isNotNull);
    });

    test('a altura do card é sempre a foto mais o texto', () {
      for (final disponivel in <double>[200, 300, 640, 1200, 2400]) {
        final largura = ProductCardMetrics.cardWidth(disponivel);
        expect(
          ProductCardMetrics.cardHeight(disponivel),
          closeTo(
            ProductCardMetrics.photoHeightFor(largura) +
                ProductCardMetrics.textHeight,
            0.001,
          ),
        );
        // A coluna nunca passa do teto — senão a foto viraria um painel.
        expect(largura, lessThanOrEqualTo(ProductCardMetrics.maxCardWidth));
      }
    });
  });
}
